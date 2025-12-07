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
# 1. AUTH (Đăng ký, Đăng nhập, Profile)
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
    return render_template('auth/profile.html', user_info=user_info)

# ==========================================
# 2. TRANG CHỦ & TÌM KIẾM
# ==========================================

@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy tham số bộ lọc
    tu_khoa = request.args.get('tu_khoa')
    vi_tri = request.args.get('vi_tri')
    muc_gia = request.args.get('muc_gia')
    loai_phong = request.args.get('loai_phong')
    
    # Câu lệnh cơ bản: Chỉ lấy bài đã duyệt
    sql = "SELECT * FROM phong_tro WHERE is_approved = 1"
    params = [] 

    # 1. Tìm kiếm từ khóa
    if tu_khoa:
        sql += " AND (ten LIKE %s OR dia_chi LIKE %s OR mo_ta LIKE %s)"
        s = f"%{tu_khoa}%"
        params.extend([s, s, s])
    
    # 2. Lọc Vị trí
    if vi_tri:
        sql += " AND dia_chi LIKE %s"
        params.append(f"%{vi_tri}%")

    # 3. Lọc Giá tiền (Xử lý dấu chấm)
    if muc_gia:
        try:
            min_gia, max_gia = muc_gia.split('-')
            sql += " AND CAST(REPLACE(gia, '.', '') AS UNSIGNED) BETWEEN %s AND %s"
            params.extend([min_gia, max_gia])
        except:
            pass

    # 4. Lọc Loại phòng
    if loai_phong:
        sql += " AND loai_phong = %s"
        params.append(loai_phong)
    
    sql += " ORDER BY id DESC"
    cursor.execute(sql, params)
    danh_sach = cursor.fetchall()
    conn.close()
    
    return render_template('index.html', danh_sach=danh_sach)

@app.route('/chitiet/<int:id_phong>')
def chitiet(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Thông tin phòng + Chủ trọ
    sql = """
        SELECT phong_tro.*, users.full_name, users.phone, users.email
        FROM phong_tro 
        JOIN users ON phong_tro.user_id = users.id 
        WHERE phong_tro.id = %s
    """
    cursor.execute(sql, (id_phong,))
    phong = cursor.fetchone()
    
    if not phong:
        conn.close()
        return "Không tìm thấy phòng này!", 404

    # 2. Bình luận
    sql_bl = """
        SELECT binh_luan.*, users.full_name 
        FROM binh_luan 
        JOIN users ON binh_luan.user_id = users.id 
        WHERE binh_luan.post_id = %s 
        ORDER BY binh_luan.id DESC
    """
    cursor.execute(sql_bl, (id_phong,))
    ds_binh_luan = cursor.fetchall()

    # 3. Tiện ích
    sql_ti = """
        SELECT tien_ich.* FROM tien_ich 
        JOIN phong_tien_ich ON tien_ich.id = phong_tien_ich.tien_ich_id 
        WHERE phong_tien_ich.phong_id = %s
    """
    cursor.execute(sql_ti, (id_phong,))
    ds_tien_ich = cursor.fetchall()

    # 4. Danh sách ảnh phụ (Slideshow)
    cursor.execute("SELECT * FROM hinh_anh_phong WHERE phong_id = %s", (id_phong,))
    ds_anh = cursor.fetchall()

    # 5. Kiểm tra Yêu thích (Đã lưu chưa?)
    da_luu = False
    if current_user.is_authenticated:
        cursor.execute("SELECT * FROM yeu_thich WHERE user_id = %s AND post_id = %s", (current_user.id, id_phong))
        if cursor.fetchone():
            da_luu = True

    conn.close()
    
    return render_template('chitiet.html', phong=phong, binh_luan=ds_binh_luan, tien_ich=ds_tien_ich, ds_anh=ds_anh, da_luu=da_luu)

# ==========================================
# 3. TƯƠNG TÁC (Chat, Yêu thích, Bình luận)
# ==========================================

@app.route('/gui_lien_he/<int:id_phong>', methods=['POST'])
@login_required
def gui_lien_he(id_phong):
    if current_user.role != 'student': return "Chức năng này chỉ dành cho Sinh viên!", 403

    noi_dung = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tạo cuộc hội thoại
    sql = "INSERT INTO lien_he (post_id, user_id, message, status) VALUES (%s, %s, %s, 'Chờ phản hồi')"
    cursor.execute(sql, (id_phong, current_user.id, noi_dung))
    lien_he_id = cursor.lastrowid
    
    # Tạo tin nhắn đầu tiên
    sql_msg = "INSERT INTO tin_nhan (lien_he_id, sender_id, message) VALUES (%s, %s, %s)"
    cursor.execute(sql_msg, (lien_he_id, current_user.id, noi_dung))
    
    conn.commit()
    conn.close()
    flash('Đã gửi yêu cầu liên hệ thành công!')
    return redirect(f'/chitiet/{id_phong}')

@app.route('/chat/<int:lien_he_id>', methods=['GET', 'POST'])
@login_required
def chat(lien_he_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    sql_check = """
        SELECT lien_he.*, 
               phong_tro.ten as ten_phong, phong_tro.user_id as chu_tro_id,
               u_sv.full_name as ten_sv, u_ct.full_name as ten_ct
        FROM lien_he
        JOIN phong_tro ON lien_he.post_id = phong_tro.id
        JOIN users u_sv ON lien_he.user_id = u_sv.id
        JOIN users u_ct ON phong_tro.user_id = u_ct.id
        WHERE lien_he.id = %s
    """
    cursor.execute(sql_check, (lien_he_id,))
    hoi_thoai = cursor.fetchone()

    if not hoi_thoai: return "Không tìm thấy!", 404
    if current_user.id != hoi_thoai['user_id'] and current_user.id != hoi_thoai['chu_tro_id']:
        return "Không có quyền truy cập!", 403

    if request.method == 'POST':
        noi_dung = request.form['message']
        if noi_dung:
            cursor.execute("INSERT INTO tin_nhan (lien_he_id, sender_id, message) VALUES (%s, %s, %s)", 
                           (lien_he_id, current_user.id, noi_dung))
            if current_user.id == hoi_thoai['chu_tro_id']:
                cursor.execute("UPDATE lien_he SET status='Đã phản hồi' WHERE id=%s", (lien_he_id,))
            conn.commit()
            return redirect(f'/chat/{lien_he_id}')

    sql_msg = """
        SELECT tin_nhan.*, users.full_name 
        FROM tin_nhan 
        JOIN users ON tin_nhan.sender_id = users.id 
        WHERE lien_he_id = %s 
        ORDER BY created_at ASC
    """
    cursor.execute(sql_msg, (lien_he_id,))
    ds_tin_nhan = cursor.fetchall()
    conn.close()

    return render_template('chat.html', 
                           lien_he_id=lien_he_id, 
                           ds_tin_nhan=ds_tin_nhan,
                           phong={'ten': hoi_thoai['ten_phong']},
                           chu_tro={'full_name': hoi_thoai['ten_ct']},
                           sinh_vien={'full_name': hoi_thoai['ten_sv']})

@app.route('/gui_binh_luan/<int:id_phong>', methods=['POST'])
@login_required
def gui_binh_luan(id_phong):
    if current_user.role != 'student': return "Chủ trọ không được tự bình luận!", 403
    rating = request.form.get('rating')
    noi_dung = request.form.get('noi_dung')
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO binh_luan (post_id, user_id, rating, noi_dung) VALUES (%s, %s, %s, %s)"
    cursor.execute(sql, (id_phong, current_user.id, rating, noi_dung))
    conn.commit()
    conn.close()
    return redirect(f'/chitiet/{id_phong}')

@app.route('/luu-tin/<int:id_phong>')
@login_required
def luu_tin(id_phong):
    if current_user.role != 'student': return "Chỉ dành cho Sinh viên!", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM yeu_thich WHERE user_id = %s AND post_id = %s", (current_user.id, id_phong))
    if cursor.fetchone():
        cursor.execute("DELETE FROM yeu_thich WHERE user_id = %s AND post_id = %s", (current_user.id, id_phong))
        flash('Đã bỏ lưu tin này!')
    else:
        cursor.execute("INSERT INTO yeu_thich (user_id, post_id) VALUES (%s, %s)", (current_user.id, id_phong))
        flash('Đã lưu vào danh sách yêu thích!')
    
    conn.commit()
    conn.close()
    return redirect(request.referrer)

@app.route('/danh-sach-yeu-thich')
@login_required
def danh_sach_yeu_thich():
    if current_user.role != 'student': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT phong_tro.* FROM phong_tro 
        JOIN yeu_thich ON phong_tro.id = yeu_thich.post_id 
        WHERE yeu_thich.user_id = %s ORDER BY yeu_thich.id DESC
    """
    cursor.execute(sql, (current_user.id,))
    ds_yeu_thich = cursor.fetchall()
    conn.close()
    return render_template('nguoi_thue/yeuthich.html', ds_yeu_thich=ds_yeu_thich)

@app.route('/lich-su')
@login_required
def lich_su():
    if current_user.role != 'student': return "Lỗi quyền hạn!", 403
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
    return render_template('nguoi_thue/lichsu.html', lich_su=lich_su_data)

# ==========================================
# 4. CHỨC NĂNG CHỦ TRỌ
# ==========================================

@app.route('/dangtin', methods=['GET', 'POST'])
@login_required
def dangtin():
    if current_user.role != 'landlord' and current_user.role != 'admin': return "Lỗi quyền hạn!", 403

    conn = get_db_connection()

    if request.method == 'POST':
        ten = request.form['ten']
        gia = request.form['gia']
        dien_tich = request.form['dien_tich']
        dia_chi = request.form['dia_chi']
        mo_ta = request.form['mo_ta']
        loai_phong = request.form['loai_phong']
        
        ten_anh = 'phong1.jpg'
        if 'hinh_anh' in request.files:
            file = request.files['hinh_anh']
            if file.filename != '':
                ten_goc = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], ten_goc))
                ten_anh = ten_goc

        cursor = conn.cursor()
        # 1. Lưu Phòng
        sql = """
            INSERT INTO phong_tro (ten, gia, dien_tich, dia_chi, anh, mo_ta, user_id, is_approved, status, loai_phong) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'con_phong', %s)
        """
        val = (ten, gia, dien_tich, dia_chi, ten_anh, mo_ta, current_user.id, loai_phong)
        cursor.execute(sql, val)
        phong_id_moi = cursor.lastrowid 
        
        # 2. Lưu Tiện ích
        ds_tien_ich = request.form.getlist('tien_ich')
        for ti_id in ds_tien_ich:
            cursor.execute("INSERT INTO phong_tien_ich (phong_id, tien_ich_id) VALUES (%s, %s)", (phong_id_moi, ti_id))

        # 3. Lưu Ảnh Phụ (Nhiều ảnh)
        if 'anh_phu' in request.files:
            files = request.files.getlist('anh_phu')
            for file in files:
                if file and file.filename != '':
                    ten_anh_phu = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], ten_anh_phu))
                    cursor.execute("INSERT INTO hinh_anh_phong (phong_id, ten_anh) VALUES (%s, %s)", (phong_id_moi, ten_anh_phu))

        conn.commit()
        conn.close()
        return redirect('/quanlytin')

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tien_ich")
    ds_tien_ich = cursor.fetchall()
    conn.close()
    return render_template('chu_tro/dangtin.html', ds_tien_ich=ds_tien_ich)

@app.route('/quanlytin')
@login_required
def quanlytin():
    if current_user.role != 'landlord' and current_user.role != 'admin': return "Lỗi quyền hạn", 403
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
    return render_template('chu_tro/quanlytin.html', danh_sach_cua_toi=danh_sach)

@app.route('/xem-lien-he/<int:id_phong>')
@login_required
def xem_lien_he(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    phong = cursor.fetchone()
    if not phong: return "Lỗi quyền hạn!", 403
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
    return render_template('chu_tro/danhsachlienhe.html', phong=phong, ds_lien_he=ds_lien_he)

@app.route('/xoatin/<int:id_phong>')
@login_required
def xoatin(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Logic xóa: Xóa tất cả dữ liệu con (ảnh, tiện ích, chat) trước khi xóa bài đăng
    try:
        # Nếu đã set ON DELETE CASCADE trong SQL thì chỉ cần xóa phong_tro
        if current_user.role == 'admin':
            cursor.execute("DELETE FROM phong_tro WHERE id = %s", (id_phong,))
        else:
            cursor.execute("DELETE FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
        conn.commit()
    except Exception as e:
        print(f"Lỗi xóa tin: {e}")
        conn.rollback()
        
    conn.close()
    return redirect('/quanlytin')

@app.route('/doi-trang-thai/<int:id_phong>')
@login_required
def doi_trang_thai(id_phong):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM phong_tro WHERE id = %s AND user_id = %s", (id_phong, current_user.id))
    phong = cursor.fetchone()
    if not phong: return "Lỗi quyền hạn", 403
    trang_thai_moi = 'da_thue' if phong['status'] == 'con_phong' else 'con_phong'
    cursor = conn.cursor()
    cursor.execute("UPDATE phong_tro SET status = %s WHERE id = %s", (trang_thai_moi, id_phong))
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
        return "Lỗi quyền hạn", 403

    if request.method == 'POST':
        ten_moi = request.form['ten']
        gia_moi = request.form['gia']
        dien_tich_moi = request.form['dien_tich']
        dia_chi_moi = request.form['dia_chi']
        mo_ta_moi = request.form['mo_ta']
        loai_phong_moi = request.form['loai_phong']
        
        sql = "UPDATE phong_tro SET ten=%s, gia=%s, dien_tich=%s, dia_chi=%s, mo_ta=%s, loai_phong=%s WHERE id=%s"
        cursor.execute(sql, (ten_moi, gia_moi, dien_tich_moi, dia_chi_moi, mo_ta_moi, loai_phong_moi, id_phong))
        conn.commit()
        conn.close()
        return redirect('/quanlytin')

    conn.close()
    return render_template('chu_tro/suatin.html', phong=phong_can_sua)

# ==========================================
# 5. ADMIN (Quản trị viên)
# ==========================================

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
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
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/delete/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Xóa sạch dữ liệu liên quan
        cursor.execute("DELETE FROM phong_tro WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM binh_luan WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM lien_he WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM tin_nhan WHERE sender_id = %s", (user_id,))
        cursor.execute("DELETE FROM yeu_thich WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        flash('Đã xóa người dùng và dữ liệu liên quan!')
    except Exception as e:
        flash(f'Lỗi khi xóa: {e}')
    finally:
        conn.close()
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
        if isinstance(o, (datetime.date, datetime)): return o.isoformat()
    response_data = json.dumps(backup_data, default=default, indent=4, ensure_ascii=False)
    return Response(response_data, mimetype="application/json", headers={"Content-disposition": "attachment; filename=backup_data.json"})

@app.route('/admin/utilities')
@login_required
def admin_utilities():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tien_ich")
    tien_ich_list = cursor.fetchall()
    conn.close()
    return render_template('admin/tien_ich.html', tien_ich_list=tien_ich_list)

@app.route('/admin/utilities/add', methods=['POST'])
@login_required
def admin_add_utility():
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    ten = request.form['ten']
    icon = request.form['icon']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tien_ich (ten_tien_ich, icon) VALUES (%s, %s)", (ten, icon))
    conn.commit()
    conn.close()
    return redirect('/admin/utilities')

@app.route('/admin/utilities/delete/<int:id>')
@login_required
def admin_delete_utility(id):
    if current_user.role != 'admin': return "Lỗi quyền hạn", 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tien_ich WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin/utilities')

if __name__ == '__main__':
    app.run(debug=True)