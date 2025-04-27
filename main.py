from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash,request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user,login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse,urljoin
from forms import CreatePostForm,RegisterForm,LoginForm,CommentForm
from smtplib import SMTP
import os


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)
MY_EMAIL = os.environ.get("MY_EMAIL")
MY_PASSWORD = os.environ.get("MY_PASS")

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view="/login"

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User,user_id)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI","sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id : Mapped[int] = mapped_column(Integer,db.ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    author = relationship("User",back_populates="posts")
    comments = relationship("Comment",back_populates="parent_post")


# TODO: Create a User table for all your registered users.
class User(db.Model,UserMixin):
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    name: Mapped[str] = mapped_column(String,nullable=False)
    email : Mapped[str] = mapped_column(String,unique=True,nullable=False)
    password: Mapped[str] = mapped_column(String,nullable=False)

    posts = relationship("BlogPost",back_populates="author")
    comments = relationship("Comment",back_populates="comment_author")

class Comment(db.Model):
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    text: Mapped[str] = mapped_column(String,nullable=False)
    comment_author_id: Mapped[int] = mapped_column(Integer,db.ForeignKey("user.id"))
    post_id: Mapped[int] = mapped_column(Integer,db.ForeignKey("blog_posts.id"))
    comment_author = relationship("User",back_populates="comments")
    parent_post = relationship("BlogPost",back_populates="comments")

with app.app_context():
    db.create_all()


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register',methods=["GET","POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email==form.email.data)).scalar()
        if not user:
            new_user = User(name=form.name.data,email=form.email.data,password=generate_password_hash(password=form.password.data,method="pbkdf2:sha256",salt_length=8))
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login"))
        else:
            flash(message="This email already exists, login instead")
            return redirect(url_for("login"))
    return render_template("register.html",form=form)

def is_safe_host(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url,target))
    return (ref_url.scheme==test_url.scheme and ref_url.netloc==test_url.netloc)

@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email==form.email.data)).scalar()
        if not user:
            flash(message="No user found with this email id.")
            return redirect(url_for("login"))
        elif not check_password_hash(pwhash=user.password,password=form.password.data):
            flash(message="Wrong Password")
            return redirect(url_for("login"))
        else:
            login_user(user,remember=form.remember.data)
            next_page = request.args.get("next")
            if not next_page or not is_safe_host(next_page):
                return redirect(url_for("get_all_posts"))
            else:
                return redirect(next_page)
    return render_template("login.html",form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>",methods=["GET","POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = Comment(text=form.comment.data,comment_author=current_user,parent_post=requested_post)
            db.session.add(new_comment)
            db.session.commit()
        else:
            flash("You are not logged in yet;")
            return redirect(url_for("login",next=request.path))
    return render_template("post.html", post=requested_post,form=form)

def admin_only(f):
    @wraps(f)
    def decorated_function(*args,**kwargs):
        if current_user.id!=1:
            return abort(403)
        return f(*args,**kwargs)
    return decorated_function

# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@login_required
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@login_required
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact",methods=["GET","POST"])
def contact():
    if request.method=="POST":
        with SMTP(host="smtp.gmail.com",port=587) as connection:
            connection.starttls()
            connection.login(user=MY_EMAIL,password=MY_PASSWORD)
            connection.sendmail(from_addr=request.form["email"],to_addrs=MY_EMAIL,msg=f"Subject:Query on your Blog Website\n\n{request.form["message"]}")
            return redirect(url_for("get_all_posts"))
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=False, port=5000)
