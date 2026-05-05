import sqlite3

def init_database():
    conn = sqlite3.connect('second_hand.db')
    cursor = conn.cursor()

    # 建表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user (
        user_id TEXT PRIMARY KEY,
        user_name TEXT NOT NULL,
        phone TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS item (
        item_id TEXT PRIMARY KEY,
        item_name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        status INTEGER NOT NULL DEFAULT 0,
        seller_id TEXT NOT NULL,
        FOREIGN KEY (seller_id) REFERENCES user(user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT UNIQUE NOT NULL,
        buyer_id TEXT NOT NULL,
        order_date TEXT NOT NULL,
        FOREIGN KEY (item_id) REFERENCES item(item_id),
        FOREIGN KEY (buyer_id) REFERENCES user(user_id)
    )
    ''')

    # 插入初始用户
    cursor.execute("INSERT OR IGNORE INTO user VALUES ('u001', 'ZhangSan', '13800000001')")
    cursor.execute("INSERT OR IGNORE INTO user VALUES ('u002', 'LiSi', '13800000002')")
    cursor.execute("INSERT OR IGNORE INTO user VALUES ('u003', 'WangWu', '13800000003')")
    cursor.execute("INSERT OR IGNORE INTO user VALUES ('u004', 'ZhaoLiu', '13800000004')")

    # 插入初始商品
    cursor.execute("INSERT OR IGNORE INTO item VALUES ('i001', 'CalculusBook', 'Book', 200, 0, 'u001')")
    cursor.execute("INSERT OR IGNORE INTO item VALUES ('i002', 'DeskLamp', 'DailyGoods', 35, 1, 'u002')")
    cursor.execute("INSERT OR IGNORE INTO item VALUES ('i003', 'Microcontroller', 'Electronics', 800, 0, 'u001')")
    cursor.execute("INSERT OR IGNORE INTO item VALUES ('i004', 'Chair', 'Furniture', 50, 1, 'u003')")
    cursor.execute("INSERT OR IGNORE INTO item VALUES ('i005', 'WaterBottle', 'DailyGoods', 15, 0, 'u004')")

    # 插入部分订单
    cursor.execute("INSERT OR IGNORE INTO orders (item_id, buyer_id, order_date) VALUES ('i002', 'u001', '2026-05-01')")
    cursor.execute("INSERT OR IGNORE INTO orders (item_id, buyer_id, order_date) VALUES ('i004', 'u002', '2026-05-02')")

    # 创建视图
    cursor.execute('''
    CREATE VIEW IF NOT EXISTS sold_items_view AS
    SELECT i.item_name, o.buyer_id
    FROM item i
    JOIN orders o ON i.item_id = o.item_id
    WHERE i.status = 1
    ''')

    cursor.execute('''
    CREATE VIEW IF NOT EXISTS unsold_items_view AS
    SELECT item_name, category, price
    FROM item
    WHERE status = 0
    ''')

    conn.commit()
    conn.close()
    print("数据库初始化成功！")

if __name__ == '__main__':
    init_database()