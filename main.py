import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import json
import pandas as pd

# --- CẤU HÌNH ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')


# --- HÀM XỬ LÝ ---
def extract_with_gemini(image):
    prompt = """Phân tích hóa đơn này và trả về JSON.
    LƯU Ý QUAN TRỌNG: Định dạng ngày (date) PHẢI là YYYY-MM-DD HH:MM:SS (ví dụ: 2026-04-14 09:20:40).
    Cấu trúc: {shop_name, date, total_amount, items: [{name, price, qty, total}]}
    Chỉ trả về JSON thuần túy.
    """

    response = model.generate_content([prompt, image])

    # Lấy text trả về
    text_response = response.text

    # In ra terminal để bạn kiểm tra nếu lỗi lại xảy ra
    print(f"Gemini Response: {text_response}")

    # Làm sạch chuỗi
    clean_json = text_response.replace('```json', '').replace('```', '').strip()

    try:
        return json.loads(clean_json)
    except json.JSONDecodeError:
        st.error("Gemini không trả về định dạng JSON chuẩn. Nội dung nhận được:")
        st.code(text_response)  # Hiển thị nội dung lỗi ngay trên giao diện web
        return None


def save_to_db(data):
    # Insert Invoice
    inv = supabase.table("invoices").insert({
        "shop_name": data['shop_name'],
        "invoice_date": data.get('date'),
        "total_amount": data['total_amount']
    }).execute()

    # Insert Items
    if inv.data:
        inv_id = inv.data[0]['id']
        items = [{**item, "invoice_id": inv_id, "product_name": item['name'], "unit_price": item['price'], "quantity": item['qty'],
                  "amount": item['total']} for item in data['items']]
        # Chỉnh sửa key cho khớp với DB
        for i in items:
            i.pop('name', None);
            i.pop('price', None);
            i.pop('qty', None);
            i.pop('total', None)

        supabase.table("invoice_items").insert(items).execute()
        return True
    return False


# --- GIAO DIỆN ---
st.set_page_config(page_title="AI Invoice Manager", layout="wide")
st.title("📑 AI Scan Hóa Đơn & Supabase")

menu = ["Scan Hóa Đơn", "Lịch Sử"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Scan Hóa Đơn":
    uploaded_file = st.file_uploader("Tải ảnh hóa đơn", type=['png', 'jpg', 'jpeg', 'jfif'])
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, width=400)

        if st.button("Xử lý và Lưu"):
            data = extract_with_gemini(img)
            if data:
                st.subheader("🔍 Kết quả trích xuất")

                # Sử dụng Markdown để tên cửa hàng có thể hiển thị đầy đủ và xuống dòng
                st.markdown(f"### 🏠 {data['shop_name']}")

                # Chỉ dùng cột cho Ngày và Tổng tiền để giao diện cân đối
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**📅 Ngày:** {data.get('date', '---')}")
                with c2:
                    # Hiển thị số tiền to, rõ ràng
                    st.markdown(
                        f"**💰 Tổng tiền:** <span style='color:green; font-size:20px; font-weight:bold;'>{data['total_amount']:,} VNĐ</span>",
                        unsafe_allow_html=True)

                # Hiển thị bảng sản phẩm
                st.write("---")
                st.write("**Danh sách sản phẩm:**")
                df_items = pd.DataFrame(data['items'])
                # Đổi tên cột hiển thị cho thân thiện
                df_items.columns = ['Tên sản phẩm', 'Giá', 'Số lượng', 'Số tiền']
                st.table(df_items)  # Dùng st.table để hiện bảng tĩnh đẹp mắt

                if save_to_db(data):
                    st.success("Đã lưu vào Supabase thành công!")
                    st.balloons()

elif choice == "Lịch Sử":
    st.header("📋 Lịch sử hóa đơn")

    # 1. Truy vấn danh sách hóa đơn (sắp xếp mới nhất lên đầu)
    res = supabase.table("invoices").select("*, invoice_items(*)").order("id", desc=True).execute()

    if res.data:
        for inv in res.data:
            # Tạo tiêu đề cho mỗi dòng hóa đơn
            label = f"🏠 {inv['shop_name']} | 📅 {inv['invoice_date']} | 💰 {inv['total_amount']:,} VNĐ"

            # Mỗi hóa đơn nằm trong một expander (nhấn vào để mở rộng)
            with st.expander(label):
                st.write(f"**ID hóa đơn:** {inv['id']}")
                st.write(f"**Cửa hàng:** {inv['shop_name']}")
                st.write(f"**Ngày hóa đơn:** {inv['invoice_date']}")
                st.write(f"**Tổng tiền:** {inv['total_amount']:,} VNĐ")

                # Hiển thị bảng chi tiết sản phẩm của hóa đơn đó
                if inv['invoice_items']:
                    st.write("---")
                    st.write("**Chi tiết sản phẩm:**")
                    df_detail = pd.DataFrame(inv['invoice_items'])

                    # Chọn và đổi tên các cột cần thiết để hiển thị
                    df_display = df_detail[['product_name', 'unit_price', 'quantity', 'amount']]
                    df_display.columns = ['Tên sản phẩm', 'Giá', 'Số lượng', 'Số tiền']

                    st.dataframe(df_display, use_container_width=True)
                else:
                    st.info("Không có dữ liệu chi tiết sản phẩm.")
    else:
        st.write("Chưa có hóa đơn nào được lưu.")