import time
import pandas as pd
import streamlit as st

st.set_page_config(page_title="أوتوميشن نسك", layout="wide")

st.title("🕋 منصة التسجيل الآلي لتطبيق نسك")
st.write("ارفع ملف الإكسيل لبدء توزيع البيانات على المحاكيات تلقائياً.")

# 1. زر رفع ملف الإكسيل
uploaded_file = st.file_uploader(
    "اختر ملف الإكسيل (XLSX)", type=["xlsx", "xls"]
)

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.subheader("📋 بيانات المعتمرين:")

    # مكان عرض الجدول لايف
    table_placeholder = st.empty()
    table_placeholder.dataframe(df)

    if st.button("🚀 بدء تشغيل الأوتوميشن"):
        progress_bar = st.progress(0)

        for index, row in df.iterrows():
            st.info(f"جاري تسجيل: {row['الاسم']}...")

            # هنا بنستدعي دالة التسجيل داخل LDPlayer
            # register_account(row['الاسم'], row['البريد الإلكتروني'], ...)
            time.sleep(2)  # محاكاة وقت التسجيل

            df.at[index, "حالة الحجز"] = "تم بنجاح"
            table_placeholder.dataframe(df)
            progress_bar.progress((index + 1) / len(df))

        st.success("🎉 تم الانتهاء من تسجيل كافة المعتمرين بنجاح!")
