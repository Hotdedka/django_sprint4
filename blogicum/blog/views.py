from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import redirect
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt

from .forms import PostForm, ProfileEditForm, CommentForm
from .models import Post, Category, Comment, User


def get_posts(post_objects):
    """Посты из БД."""
    print(f"DEBUG: get_posts called with {post_objects.count()} posts")  # Изменить на count()
    filtered_posts = post_objects.filter(
        pub_date__lte=timezone.now(),
        is_published=True,
        category__is_published=True
    ).annotate(comment_count=Count('comments'))
    print(f"DEBUG: get_posts returning {len(filtered_posts)} posts")
    return filtered_posts


def get_paginator(request, items, num=10):
    """Создает объект пагинации."""
    paginator = Paginator(items, num)
    num_pages = request.GET.get('page')
    return paginator.get_page(num_pages)


def index(request):
    """Главная страница."""
    template = 'blog/index.html'
    post_list = get_posts(Post.objects).order_by('-pub_date')
    page_obj = get_paginator(request, post_list)
    context = {'page_obj': page_obj}
    return render(request, template, context)


def post_detail(request, post_id):
    """Полное описание выбранной записи."""
    template = 'blog/detail.html'
    print(f"DEBUG: post_detail called with post_id={post_id}")
    posts = get_object_or_404(Post, id=post_id)
    print(f"DEBUG: post found: {posts.id}, pub_date: {posts.pub_date}, is_published: {posts.is_published}")
    
    # Проверяем права доступа только если пользователь не автор
    if request.user != posts.author:
        # Проверяем, что пост опубликован и доступен для просмотра
        if not (posts.is_published and 
                  posts.category.is_published and 
                  posts.pub_date <= timezone.now()):
            raise Http404("Пост не найден")
        print(f"DEBUG: filtered post found: {posts.id}, pub_date: {posts.pub_date}")
    
    comments = posts.comments.order_by('created_at')
    form = CommentForm()
    print(f"DEBUG: post_detail - user: {request.user}, authenticated: {request.user.is_authenticated}")
    print(f"DEBUG: post_detail - form: {form}")
    context = {'post': posts, 'form': form, 'comments': comments}
    return render(request, template, context)

def category_posts(request, category_slug):
    """Публикация категории."""
    template = 'blog/category.html'
    category = get_object_or_404(
        Category, slug=category_slug, is_published=True)
    post_list = get_posts(category.posts).order_by('-pub_date')
    page_obj = get_paginator(request, post_list)
    context = {'category': category, 'page_obj': page_obj}
    return render(request, template, context)

@csrf_exempt
@login_required
def create_post(request):
    """Создает новую запись."""
    template = 'blog/create.html'
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()
            return redirect('blog:profile', username=request.user.username)
    else:
        form = PostForm()
    context = {'form': form}
    return render(request, template, context)


def profile(request, username):
    """Возвращает профиль пользователя."""
    template = 'blog/profile.html'
    user = get_object_or_404(User, username=username)

    # Базовый запрос
    posts_query = user.posts.annotate(comment_count=Count('comments'))

    # КТО СМОТРИТ ПРОФИЛЬ?
    is_own_profile = request.user == user
    is_admin = request.user.is_authenticated and request.user.is_staff

    if is_own_profile or is_admin:
        # Автор или админ видят все посты (включая снятые)
        posts_list = posts_query.order_by('-pub_date')
    else:
        # Остальные видят только опубликованные
        posts_list = posts_query.filter(
            is_published=True,
            pub_date__lte=timezone.now(),
            category__is_published=True
        ).order_by('-pub_date')

    page_obj = get_paginator(request, posts_list)
    context = {'profile': user, 'page_obj': page_obj}
    return render(request, template, context)

@csrf_exempt
@login_required
def edit_profile(request):
    """Редактирует профиль пользователя."""
    template = 'blog/user.html'
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('blog:profile', username=request.user.username)
        else:
            print(f"Form errors: {form.errors}")
    else:
        form = ProfileEditForm(instance=request.user)
    context = {'form': form}
    return render(request, template, context)


@login_required
def edit_post(request, post_id):
    """Редактирует запись блога."""
    template = 'blog/create.html'
    post = get_object_or_404(Post, id=post_id)
    if request.user != post.author:
        return redirect('blog:post_detail', post_id=post_id)
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES or None, instance=post)
        if form.is_valid():
            post = form.save()
            return redirect('blog:post_detail', post_id=post_id)
    else:
        form = PostForm(instance=post)
    context = {'form': form}
    return render(request, template, context)


@login_required
def delete_post(request, post_id):
    """Удаляет запись блога."""
    template = 'blog/create.html'
    post = get_object_or_404(Post, id=post_id)
    if request.user != post.author:
        return redirect('blog:post_detail', post_id=post_id)
    if request.method == 'POST':
        post.delete()
        return redirect('blog:index')
    else:
        form = PostForm(instance=post)
    context = {'form': form}
    return render(request, template, context)


@login_required
def add_comment(request, post_id):
    """Добавляет комментарий к записи."""
    print(f"DEBUG: add_comment called - user: {request.user}, post_id: {post_id}")
    try:
        post = get_object_or_404(Post, id=post_id)
    except Http404:
        raise Http404("Пост не найден")
    
    if request.method == 'POST':
        form = CommentForm(request.POST)
        print(f"DEBUG: add_comment - form is_valid: {form.is_valid()}")
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            print(f"DEBUG: add_comment - comment saved with id: {comment.id}")
            return redirect('blog:post_detail', post_id=post_id)
        else:
            print(f"Comment form errors: {form.errors}")
    
    return redirect('blog:post_detail', post_id=post_id)

@login_required
def edit_comment(request, post_id, comment_id):
    """Редактирует комментарий."""
    template = 'blog/comment.html'
    comment = get_object_or_404(Comment, id=comment_id)
    if request.user != comment.author:
        return redirect('blog:post_detail', post_id=post_id)
    if request.method == "POST":
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('blog:post_detail', post_id=post_id)
    else:
        form = CommentForm(instance=comment)
    context = {'form': form, 'comment': comment}
    return render(request, template, context)


@login_required
def delete_comment(request, post_id, comment_id):
    """Удаляет комментарий."""
    template = 'blog/comment.html'
    comment = get_object_or_404(Comment, id=comment_id)
    if request.user != comment.author:
        return redirect('blog:post_detail', post_id=post_id)
    if request.method == "POST":
        comment.delete()
        return redirect('blog:post_detail', post_id=post_id)
    context = {'comment': comment}
    return render(request, template, context)