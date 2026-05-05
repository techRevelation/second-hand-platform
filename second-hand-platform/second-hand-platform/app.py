from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import date
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'change_this_to_a_random_secret_key'

def get_db_connection():
    conn = sqlite3.connect('second_hand.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # 开启 WAL 模式，利于并发和崩溃恢复
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# ───────────────── 简易角色管理 ─────────────────
@app.route('/login/<role>')
def login(role):
    if role in ['admin', 'user']:
        session['role'] = role
        session['username'] = '管理员' if role == 'admin' else '普通用户'
        flash(f'已切换为 {role} 身份')
    else:
        flash('无效角色', 'error')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录')
    return redirect(url_for('index'))

# 权限装饰器：仅管理员可调用
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('权限不足：仅管理员可执行此操作', 'error')
            return redirect(url_for('items'))
        return f(*args, **kwargs)
    return decorated_function

# ───────────────── 首页 ─────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ───────────────── 用户列表 ─────────────────
@app.route('/users')
def users():
    conn = get_db_connection()
    users_data = conn.execute('SELECT * FROM user').fetchall()
    conn.close()
    return render_template('users.html', users=users_data)

# ───────────────── 商品列表 ─────────────────
@app.route('/items')
def items():
    conn = get_db_connection()
    items_data = conn.execute('SELECT * FROM item').fetchall()
    conn.close()
    return render_template('items.html', items=items_data)

# ───────────────── 订单列表 ─────────────────
@app.route('/orders')
def orders():
    conn = get_db_connection()
    orders_data = conn.execute('''
        SELECT o.order_id, o.item_id, i.item_name, o.buyer_id, u.user_name, o.order_date
        FROM orders o
        JOIN item i ON o.item_id = i.item_id
        JOIN user u ON o.buyer_id = u.user_id
    ''').fetchall()
    conn.close()
    return render_template('orders.html', orders=orders_data)

# ───────────────── 查询页（支持多种交互） ─────────────────
@app.route('/queries', methods=['GET'])
def queries():
    conn = get_db_connection()
    action = request.args.get('action', '')
    min_price = request.args.get('min_price', '')
    seller_id = request.args.get('seller_id', '')

    unsold_items = []
    price_gt = []
    daily_goods = []
    user_items = []
    sold_with_buyer = []
    order_details = []
    u001_sold = []

    # 基本查询
    if action == 'unsold':
        unsold_items = conn.execute('SELECT * FROM item WHERE status = 0').fetchall()
    elif action == 'price_gt' and min_price:
        try:
            price_val = float(min_price)
            price_gt = conn.execute('SELECT * FROM item WHERE price > ?', (price_val,)).fetchall()
        except ValueError:
            flash('请输入有效数字', 'error')
    elif action == 'daily_goods':
        daily_goods = conn.execute("SELECT * FROM item WHERE category = 'DailyGoods'").fetchall()
    elif action == 'user_items' and seller_id:
        user_items = conn.execute('SELECT * FROM item WHERE seller_id = ?', (seller_id,)).fetchall()
    # 连接查询
    elif action == 'sold_info':
        sold_with_buyer = conn.execute('''
            SELECT i.item_name, u.user_name
            FROM item i
            JOIN orders o ON i.item_id = o.item_id
            JOIN user u ON o.buyer_id = u.user_id
            WHERE i.status = 1
        ''').fetchall()
    elif action == 'order_detail':
        order_details = conn.execute('''
            SELECT i.item_name, u.user_name AS buyer_name, o.order_date
            FROM orders o
            JOIN item i ON o.item_id = i.item_id
            JOIN user u ON o.buyer_id = u.user_id
        ''').fetchall()
    elif action == 'u001_sold_status':
        u001_sold = conn.execute('''
            SELECT i.item_name, CASE WHEN o.item_id IS NULL THEN '未售出' ELSE '已售出' END AS status
            FROM item i
            LEFT JOIN orders o ON i.item_id = o.item_id
            WHERE i.seller_id = 'u001'
        ''').fetchall()

    # 聚合统计
    total_items = conn.execute('SELECT COUNT(*) AS cnt FROM item').fetchone()['cnt']
    category_count = conn.execute('SELECT category, COUNT(*) AS cnt FROM item GROUP BY category').fetchall()
    avg_price = conn.execute('SELECT AVG(price) AS avg_p FROM item').fetchone()['avg_p']
    most_items_user = conn.execute('''
        SELECT i.seller_id, u.user_name, COUNT(*) AS cnt
        FROM item i
        JOIN user u ON i.seller_id = u.user_id
        GROUP BY i.seller_id
        ORDER BY cnt DESC
        LIMIT 1
    ''').fetchone()

    # 视图
    sold_view = conn.execute('SELECT * FROM sold_items_view').fetchall()
    unsold_view = conn.execute('SELECT * FROM unsold_items_view').fetchall()

    conn.close()
    return render_template('queries.html',
        unsold_items=unsold_items, price_gt=price_gt,
        daily_goods=daily_goods, user_items=user_items,
        sold_with_buyer=sold_with_buyer, order_details=order_details,
        u001_sold=u001_sold,
        total_items=total_items, category_count=category_count,
        avg_price=round(avg_price, 2) if avg_price else 0,
        most_items_user=most_items_user,
        sold_view=sold_view, unsold_view=unsold_view,
        action=action, min_price=min_price, seller_id=seller_id
    )

# ───────────────── 购买（含并发控制） ─────────────────
@app.route('/buy', methods=['POST'])
def buy_item():
    if 'role' not in session:
        flash('请先登录（访问 /login/user 或 /login/admin）', 'error')
        return redirect(url_for('items'))

    item_id = request.form['item_id']
    buyer_id = request.form['buyer_id']
    conn = get_db_connection()
    conn.execute("BEGIN IMMEDIATE")   # 写锁，防止并发超卖
    try:
        item = conn.execute('SELECT status FROM item WHERE item_id = ?', (item_id,)).fetchone()
        if not item:
            flash('商品不存在', 'error')
            conn.rollback()
            return redirect(url_for('items'))
        if item['status'] == 1:
            flash('商品已售出，无法再次购买', 'error')
            conn.rollback()
            return redirect(url_for('items'))

        buyer = conn.execute('SELECT * FROM user WHERE user_id = ?', (buyer_id,)).fetchone()
        if not buyer:
            flash('买家不存在', 'error')
            conn.rollback()
            return redirect(url_for('items'))

        today = date.today().isoformat()
        conn.execute('INSERT INTO orders (item_id, buyer_id, order_date) VALUES (?, ?, ?)',
                     (item_id, buyer_id, today))
        conn.execute('UPDATE item SET status = 1 WHERE item_id = ?', (item_id,))
        conn.commit()
        flash('购买成功！')
    except sqlite3.IntegrityError:
        conn.rollback()
        flash('购买失败：商品已被他人抢先买下', 'error')
    except Exception as e:
        conn.rollback()
        flash('购买失败：系统错误', 'error')
    finally:
        conn.close()
    return redirect(url_for('items'))

# ───────────────── 新增商品（需管理员权限） ─────────────────
@app.route('/add_item', methods=['POST'])
@admin_required
def add_item():
    item_id = request.form['item_id']
    item_name = request.form['item_name']
    category = request.form['category']
    price = float(request.form['price'])
    seller_id = request.form['seller_id']
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO item (item_id, item_name, category, price, status, seller_id) VALUES (?, ?, ?, ?, 0, ?)',
                     (item_id, item_name, category, price, seller_id))
        conn.commit()
        flash('新增商品成功')
    except sqlite3.IntegrityError:
        flash('新增失败：商品ID可能重复或卖家不存在', 'error')
    finally:
        conn.close()
    return redirect(url_for('items'))

# ───────────────── 修改价格（需管理员权限） ─────────────────
@app.route('/update_price', methods=['POST'])
@admin_required
def update_price():
    item_id = request.form['item_id']
    new_price = float(request.form['new_price'])
    conn = get_db_connection()
    conn.execute('UPDATE item SET price = ? WHERE item_id = ?', (new_price, item_id))
    conn.commit()
    conn.close()
    flash('价格修改成功')
    return redirect(url_for('items'))

# ───────────────── 删除未售出商品（需管理员权限） ─────────────────
@app.route('/delete_item', methods=['POST'])
@admin_required
def delete_item():
    item_id = request.form['item_id']
    conn = get_db_connection()
    item = conn.execute('SELECT * FROM item WHERE item_id = ?', (item_id,)).fetchone()
    if item and item['status'] == 0:
        conn.execute('DELETE FROM item WHERE item_id = ?', (item_id,))
        conn.commit()
        flash('未售出商品已删除')
    else:
        flash('删除失败：商品不存在或已售出', 'error')
    conn.close()
    return redirect(url_for('items'))

# ───────────────── 启动 ─────────────────
if __name__ == '__main__':
    # 首次运行时自动初始化数据库
    if not os.path.exists('second_hand.db'):
        from init_db import init_database
        init_database()
    app.run(debug=True)