import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import mysql.connector
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.secret_key = 'khoa_bi_mat_sieu_cap' 
app.config['UPLOAD_FOLDER'] = 'static/images'

# --- CẤU HÌNH FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

# --- KẾT NỐI DB ---
def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="web_tro"
    )
    return conn

# --- CLASS USER ---
class User(UserMixin):
    def __init__(self, id, username, role, full_name):
        self.id = id
        self.username = username
        self.role = role
        self.full_name = full_name

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(id=user_data['id'], username=user_data['username'], role=user_data['role'], full_name=user_data['full_name'])
    return None

# ==========================================
# PHẦN 1: XÁC THỰC (AUTH) -> Thư mục templates/auth/
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'] 
        full_name = request.form['full_name']
        role = request.form['role']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, full_name, role) VALUES (%s, %s, %s, %s)", 
                           (username, password, full_name, role))
            conn.commit()
            return redirect(url_for('login'))
        except:
            return "Tên đăng nhập đã tồn tại!"
        finally:
            conn.close()
    # Đã sửa đường dẫn
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data:
            user = User(id=user_data['id'], username=user_data['username'], role=user_data['role'], full_name=user_data['full_name'])
            login_user(user)
            if user.role == 'admin':
                return redirect('/admin')
            return redirect('/')
        else:
            return "Sai tên đăng nhập hoặc mật khẩu!"
            
    # Đã sửa đường dẫn
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        dob = request.form.get('dob')
        gender = request.form.get('gender')
        cccd = request.form.get('cccd')

        sql = """
            UPDATE users 
            SET full_name = %s, email = %s, phone = %s, dob = %s, gender = %s, cccd = %s
            WHERE id = %s
        """
        val = (full_name, email, phone, dob, gender, cccd, current_user.id)
        cursor.execute(sql, val)
        conn.commit()
        
        flash('Cập nhật hồ sơ thành công!')
        current_user.full_name = full_name 

    cursor.execute("SELECT * FROM users WHERE id = %s", (current_user.id,))
    user_info = cursor.fetchone()
    conn.close()
    
    # Đã sửa đường dẫn
    return render_template('auth/profile.html', user_info=user_info)

# ==========================================
# PHẦN 2: CHỨC NĂNG CHUNG & NGƯỜI THUÊ -> templates/nguoi_thue/
# ==========================================

# --- TRANG CHỦ (Đã nâng cấp Bộ lọc xịn) ---
@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Lấy các tham số từ URL
    tu_khoa = request.args.get('tu_khoa')
    vi_tri = request.args.get('vi_tri')
    muc_gia = request.args.get('muc_gia')
    loai_phong = request.args.get('loai_phong')
    
    # 2. Câu lệnh SQL cơ bản
    sql = "SELECT * FROM phong_tro WHERE is_approved = 1"
    params = [] 

    # 3. Xử lý tìm kiếm từ khóa (Giữ nguyên)
    if tu_khoa:
        sql += " AND (ten LIKE %s OR dia_chi LIKE %s OR mo_ta LIKE %s)"
        s = f"%{tu_khoa}%"
        params.extend([s, s, s])
    
    # 4. Xử lý Lọc VỊ TRÍ (Tìm tương đối trong địa chỉ)
    if vi_tri:
        sql += " AND dia_chi LIKE %s"
        params.append(f"%{vi_tri}%")

    # 5. Xử lý Lọc GIÁ (Tách chuỗi "1000-2000" thành 2 số)
    if muc_gia:
        try:
            min_gia, max_gia = muc_gia.split('-')
            # Chuyển đổi cột 'gia' (đang là VARCHAR) thành số để so sánh
            # CAST(REPLACE(gia, '.', '') AS UNSIGNED) -> Xóa dấu chấm và ép kiểu số
            sql += " AND CAST(REPLACE(gia, '.', '') AS UNSIGNED) BETWEEN %s AND %s"
            params.extend([min_gia, max_gia])
        except:
            pass # Nếu lỗi định dạng giá thì bỏ qua

    # 6. Xử lý Lọc LOẠI PHÒNG (Tìm trong Tên hoặc Mô tả)
    if loai_phong:
        sql += " AND (ten LIKE %s OR mo_ta LIKE %s)"
        lp = f"%{loai_phong}%"
        params.extend([lp, lp])
    
    # Sắp xếp mới nhất
    sql += " ORDER BY id DESC"

    cursor.execute(sql, params)
    danh_sach = cursor.fetchall()
    conn.close()
    
    return render_template('index.html', danh_sach=danh_sach)
@app.route('/chitiet/<int:id_phong>')
def chitiet(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT phong_tro.*, users.full_name, users.phone, users.email
        FROM phong_tro 
        JOIN users ON phong_tro.user_id = users.id 
        WHERE phong_tro.id = %s
    """
    cursor.execute(sql, (id_phong,))
    phong = cursor.fetchone()
    
    sql_bl = """
        SELECT binh_luan.*, users.full_name 
        FROM binh_luan 
        JOIN users ON binh_luan.user_id = users.id 
        WHERE binh_luan.post_id = %s 
        ORDER BY binh_luan.id DESC
    """
    cursor.execute(sql_bl, (id_phong,))
    ds_binh_luan = cursor.fetchall()
    conn.close()
    
    if phong:
        # File chitiet.html nằm ở ngoài cùng (không đổi)
        return render_template('chitiet.html', phong=phong, binh_luan=ds_binh_luan)
    return "Không tìm thấy phòng này!", 404

@app.route('/gui_lien_he/<int:id_phong>', methods=['POST'])
@login_required
def gui_lien_he(id_phong):
    if current_user.role != 'student':
        return "Chức năng này chỉ dành cho Sinh viên tìm trọ!", 403

    noi_dung = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO lien_he (post_id, user_id, message) VALUES (%s, %s, %s)"
    cursor.execute(sql, (id_phong, current_user.id, noi_dung))
    conn.commit()
    conn.close()
    flash('Đã gửi yêu cầu liên hệ thành công!')
    return redirect(f'/chitiet/{id_phong}')

@app.route('/gui_binh_luan/<int:id_phong>', methods=['POST'])
@login_required
def gui_binh_luan(id_phong):
    if current_user.role != 'student':
        return "Chủ trọ không được tự bình luận!", 403
    rating = request.form.get('rating')
    noi_dung = request.form.get('noi_dung')
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO binh_luan (post_id, user_id, rating, noi_dung) VALUES (%s, %s, %s, %s)"
    cursor.execute(sql, (id_phong, current_user.id, rating, noi_dung))
    conn.commit()
    conn.close()
    return redirect(f'/chitiet/{id_phong}')

@app.route('/lich-su')
@login_required
def lich_su():
    if current_user.role != 'student':
        return "Trang này chỉ dành cho Sinh viên!", 403
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT lien_he.*, phong_tro.ten, phong_tro.gia, phong_tro.anh, phong_tro.id as phong_id
        FROM lien_he 
        JOIN phong_tro ON lien_he.post_id = phong_tro.id 
        WHERE lien_he.user_id = %s 
        ORDER BY lien_he.id DESC
    """
    cursor.execute(sql, (current_user.id,))
    lich_su_data = cursor.fetchall()
    conn.close()
    
    # Đã sửa đường dẫn
    return render_template('nguoi_thue/lichsu.html', lich_su=lich_su_data)

# ==========================================
# PHẦN 3: CHỨC NĂNG CHỦ TRỌ -> templates/chu_tro/
# ==========================================

@app.route('/dangtin', methods=['GET', 'POST'])
@login_required
def dangtin():
    # ... (Giữ nguyên đoạn kiểm tra quyền)

    if request.method == 'POST':
        ten = request.form['ten']
        gia = request.form['gia']
        dia_chi = request.form['dia_chi']
        mo_ta = request.form['mo_ta']
        
        # 1. LẤY DỮ LIỆU LOẠI PHÒNG
        loai_phong = request.form['loai_phong']
        
        ten_anh = 'phong1.jpg'
        if 'hinh_anh' in request.files:
            # ... (Giữ nguyên đoạn xử lý ảnh) ...
            pass # (Tôi viết tắt đoạn này, bạn giữ nguyên code ảnh cũ nhé)

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 2. CẬP NHẬT CÂU LỆNH SQL (Thêm loai_phong)
        sql = """
            INSERT INTO phong_tro (ten, gia, dia_chi, anh, mo_ta, user_id, is_approved, loai_phong) 
            VALUES (%s, %s, %s, %s, %s, %s, 0, %s)
        """
        val = (ten, gia, dia_chi, ten_anh, mo_ta, current_user.id, loai_phong)
        
        cursor.execute(sql, val)
        conn.commit()
        conn.close()
        return redirect('/quanlytin')

    return render_template('chu_tro/dangtin.html')
@app.route('/quanlytin')
@login_required
def quanlytin():
    if current_user.role != 'landlord' and current_user.role != 'admin':
        return "Chỉ chủ trọ mới được vào đây!", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT phong_tro.*, COUNT(lien_he.id) as so_luot_lien_he 
        FROM phong_tro 
        LEFT JOIN lien_he ON phong_tro.id = lien_he.post_id 
        WHERE phong_tro.user_id = %s 
        GROUP BY phong_tro.id 
        ORDER BY phong_tro.id DESC
    """
    cursor.execute(sql, (current_user.id,))
    danh_sach = cursor.fetchall()
    conn.close()
    
    # Đã sửa đường dẫn
    return render_template('chu_tro/quanlytin.html', danh_sach_cua_toi=danh_sach, user=current_user)

@app.route('/xem-lien-he/<int:id_phong>')
@login_required
def xem_lien_he(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    phong = cursor.fetchone()
    
    if not phong:
        return "Bạn không có quyền xem thông tin phòng này!", 403
        
    sql = """
        SELECT lien_he.*, users.full_name, users.phone, users.email 
        FROM lien_he 
        JOIN users ON lien_he.user_id = users.id 
        WHERE lien_he.post_id = %s 
        ORDER BY lien_he.created_at DESC
    """
    cursor.execute(sql, (id_phong,))
    ds_lien_he = cursor.fetchall()
    conn.close()
    
    # Đã sửa đường dẫn
    return render_template('chu_tro/danhsachlienhe.html', phong=phong, ds_lien_he=ds_lien_he)

@app.route('/xoatin/<int:id_phong>')
@login_required
def xoatin(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor()
    if current_user.role == 'admin':
        cursor.execute("DELETE FROM phong_tro WHERE id = %s", (id_phong,))
    else:
        cursor.execute("DELETE FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    conn.commit()
    conn.close()
    return redirect('/quanlytin')

@app.route('/suatin/<int:id_phong>', methods=['GET', 'POST'])
@login_required
def suatin(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if current_user.role == 'admin':
        cursor.execute("SELECT * FROM phong_tro WHERE id = %s", (id_phong,))
    else:
        cursor.execute("SELECT * FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    
    phong_can_sua = cursor.fetchone()
    
    if not phong_can_sua:
        conn.close()
        return "Bạn không có quyền sửa bài này!", 403

    if request.method == 'POST':
        ten_moi = request.form['ten']
        gia_moi = request.form['gia']
        dia_chi_moi = request.form['dia_chi']
        mo_ta_moi = request.form['mo_ta']
        
        # Lấy dữ liệu loại phòng
        loai_phong_moi = request.form['loai_phong'] 

        # Câu lệnh SQL (thẳng hàng với biến bên dưới)
        sql = "UPDATE phong_tro SET ten=%s, gia=%s, dia_chi=%s, mo_ta=%s, loai_phong=%s WHERE id=%s"
        
        # Dòng này phải THẲNG HÀNG với dòng sql = "..." ở trên
        cursor.execute(sql, (ten_moi, gia_moi, dia_chi_moi, mo_ta_moi, loai_phong_moi, id_phong))
        
        conn.commit()
        conn.close()
        return redirect('/quanlytin')

    conn.close()
    # Đã sửa đường dẫn
    return render_template('chu_tro/suatin.html', phong=phong_can_sua)
# --- CHỨC NĂNG ĐỔI TRẠNG THÁI (CÒN PHÒNG / HẾT PHÒNG) ---
@app.route('/doi-trang-thai/<int:id_phong>')
@login_required
def doi_trang_thai(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Kiểm tra quyền: Phải là chủ của bài đăng này
    cursor.execute("SELECT * FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    phong = cursor.fetchone()
    
    if not phong:
        conn.close()
        return "Bạn không có quyền sửa trạng thái bài này!", 403

    # 2. Logic đảo ngược trạng thái
    trang_thai_moi = 'da_thue' if phong['status'] == 'con_phong' else 'con_phong'
    
    # 3. Cập nhật vào Database
    cursor = conn.cursor()
    cursor.execute("UPDATE phong_tro SET status = %s WHERE id = %s", (trang_thai_moi, id_phong))
    conn.commit()
    conn.close()
    
    return redirect('/quanlytin')
# ==========================================
# PHẦN 4: CHỨC NĂNG ADMIN -> templates/admin/
# ==========================================

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return "Không có quyền truy cập!", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    stats = {}
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student'")
    stats['sinh_vien'] = cursor.fetchone()['cnt']
    
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role='landlord'")
    stats['chu_tro'] = cursor.fetchone()['cnt']
    
    cursor.execute("SELECT COUNT(*) as cnt FROM phong_tro")
    stats['tong_bai'] = cursor.fetchone()['cnt']
    
    cursor.execute("SELECT COUNT(*) as cnt FROM phong_tro WHERE is_approved=0")
    stats['cho_duyet'] = cursor.fetchone()['cnt']

    conn.close()
    # Đã sửa đường dẫn
    return render_template('admin/dashboard.html', stats=stats)

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    conn.close()
    # Đã sửa đường dẫn
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/delete/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    flash('Đã xóa người dùng thành công!')
    return redirect('/admin/users')

@app.route('/admin/posts')
@login_required
def admin_posts():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT phong_tro.*, users.full_name, users.username 
        FROM phong_tro 
        JOIN users ON phong_tro.user_id = users.id 
        ORDER BY phong_tro.id DESC
    """
    cursor.execute(sql)
    posts = cursor.fetchall()
    conn.close()
    # Đã sửa đường dẫn
    return render_template('admin/posts.html', posts=posts)

@app.route('/admin/duyet/<int:id_phong>')
@login_required
def duyet_bai(id_phong):
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE phong_tro SET is_approved = 1 WHERE id = %s", (id_phong,))
    conn.commit()
    conn.close()
    return redirect('/admin/posts')

@app.route('/admin/xoa/<int:id_phong>')
@login_required
def xoa_bai(id_phong):
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM phong_tro WHERE id = %s", (id_phong,))
    conn.commit()
    conn.close()
    return redirect('/admin/posts')

@app.route('/admin/backup')
@login_required
def admin_backup():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    backup_data = {}
    cursor.execute("SELECT * FROM users")
    backup_data['users'] = cursor.fetchall()
    cursor.execute("SELECT * FROM phong_tro")
    backup_data['phong_tro'] = cursor.fetchall()
    conn.close()
    
    def default(o):
        if isinstance(o, (datetime.date, datetime)):
            return o.isoformat()
            
    response_data = json.dumps(backup_data, default=default, indent=4, ensure_ascii=False)
    
    return Response(
        response_data,
        mimetype="application/json",
        headers={"Content-disposition": "attachment; filename=backup_data.json"}
    )

if __name__ == '__main__':
    app.run(debug=True)
