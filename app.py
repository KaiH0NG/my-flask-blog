# app.py (V9 - 真正最终版)

import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from flask_bcrypt import Bcrypt
import markdown
from markupsafe import Markup

# --- 基础配置 ---
app = Flask(__name__)

# --- 数据库配置 ---
database_url = os.environ.get('DATABASE_URL')
if database_url:
    database_url = database_url.replace("postgres://", "postgresql://", 1)
else:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    database_url = 'sqlite:///' + os.path.join(base_dir, 'blog.db')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_dev')

base_dir = os.path.abspath(os.path.dirname(__file__))
upload_path = os.path.join(base_dir, 'static/uploads')
if not os.path.exists(upload_path):
    os.makedirs(upload_path)

# --- 初始化插件 ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面。'
login_manager.login_message_category = 'info'

@app.template_filter('md')
def markdown_to_html(text):
    html = markdown.markdown(text, extensions=['fenced_code', 'tables'])
    return Markup(html)

# --- 数据库模型定义 ---
class SiteConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    def __repr__(self): return f"User('{self.username}')"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), nullable=False, default='Admin')
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    tags = db.Column(db.String(200), nullable=True)
    def __repr__(self): return f"Post('{self.title}')"
    def get_tags_list(self): return [tag.strip() for tag in self.tags.split(',')] if self.tags else []

# --- 我们删除了之前所有的其他代码，只保留到这里 ---
# --- 下面是完整的、正确的路由和配置 ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_site_config(key, default=None):
    config = SiteConfig.query.filter_by(key=key).first()
    return config.value if config else default

@app.context_processor
def inject_site_config():
    config_keys = ['hero_title', 'hero_subtitle', 'hero_image', 'about_text']
    site_config = {key: get_site_config(key) for key in config_keys}
    site_config['blog_name'] = get_site_config('blog_name', "Kai'blog")
    return {'site_config': site_config}

class SecureAdminView:
    def is_accessible(self): return current_user.is_authenticated
    def inaccessible_callback(self, name, **kwargs):
        flash('您没有权限访问后台管理页面，请先以管理员身份登录。', 'danger'); return redirect(url_for('login', next=request.url))

class SecureModelView(SecureAdminView, ModelView): pass
class SecureAdminIndexView(SecureAdminView, AdminIndexView): pass

class SiteConfigView(SecureAdminView, BaseView):
    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if request.method == 'POST':
            for key, value in request.form.items():
                config_item = SiteConfig.query.filter_by(key=key).first()
                if config_item: config_item.value = value
                else: db.session.add(SiteConfig(key=key, value=value))
            if 'hero_image' in request.files:
                file = request.files['hero_image']
                if file and file.filename != '':
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_path, filename)
                    file.save(filepath)
                    image_url = f'uploads/{filename}'
                    config_item = SiteConfig.query.filter_by(key='hero_image').first()
                    if config_item: config_item.value = image_url
                    else: db.session.add(SiteConfig(key='hero_image', value=image_url))
            db.session.commit()
            flash('网站设置已更新！', 'success')
            return redirect(url_for('siteconfig.index'))
        return self.render('admin/site_config.html')

admin = Admin(app, name="Kai'blog 后台", template_mode='bootstrap3', index_view=SecureAdminIndexView())
admin.add_view(SecureModelView(Post, db.session, name='文章管理'))
admin.add_view(SiteConfigView(name='网站设置', endpoint='siteconfig'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and bcrypt.check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user, remember=True); next_page = request.args.get('next')
            flash('登录成功！', 'success'); return redirect(next_page) if next_page else redirect(url_for('home'))
        else: flash('登录失败，请检查用户名和密码。', 'danger')
    return render_template('login.html', title='登录')

@app.route('/logout')
def logout():
    logout_user(); flash('您已成功退出。', 'info'); return redirect(url_for('home'))

@app.context_processor
def inject_tags():
    all_posts = Post.query.all(); all_tags_list = [tag for post in all_posts for tag in post.get_tags_list()]
    unique_tags = sorted(list(set(all_tags_list))); return dict(all_tags=unique_tags)

@app.route("/")
@app.route("/home")
def home():
    page = request.args.get('page', 1, type=int)
    pagination = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('home.html', posts=pagination.items, title='我的博客首页', pagination=pagination)

@app.route("/post/<int:post_id>")
def post(post_id):
    found_post = Post.query.get_or_404(post_id); return render_template('post.html', post=found_post, title=found_post.title)

@app.route("/tag/<string:tag_name>")
def show_tag(tag_name):
    page = request.args.get('page', 1, type=int)
    pagination = Post.query.filter(Post.tags.like(f'%{tag_name}%')).order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('home.html', posts=pagination.items, title=f"标签: {tag_name}", pagination=pagination)

from flask import send_from_directory
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(upload_path, filename)

# --- 我们删除了原来的 @event.listens_for 事件监听器 ---

# ===================== 全新的、更可靠的初始化代码 =====================
with app.app_context():
    db.create_all() # 1. 首先确保所有表都已创建

    # 2. 检查默认设置是否已存在，如果不存在，则创建
    if SiteConfig.query.count() == 0:
        print("Populating initial site config...")
        db.session.add_all([
            SiteConfig(key='blog_name', value="Kai'blog"),
            SiteConfig(key='hero_title', value='欢迎来到我的世界'),
            SiteConfig(key='hero_subtitle', value='在这里，我记录思考、分享知识、探索未知。'),
            SiteConfig(key='about_text', value='这是关于我博客的默认简介，请在后台修改。')
        ])
        db.session.commit()

    # 3. 检查 admin 用户是否已存在，如果不存在，则创建
    if not User.query.filter_by(username='admin').first():
        print("Creating default admin user...")
        hashed_password = bcrypt.generate_password_hash('112233qq').decode('utf-8')
        admin_user = User(username='admin', password_hash=hashed_password)
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user created.")
# ======================= 初始化代码结束 =======================