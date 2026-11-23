import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
import os
import json
from PIL import Image

# PDF Üretimi için ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle

# ---------------------------------------------------------
# 1. SAYFA YAPILANDIRMASI VE MOBİL UYUMLU CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sayar Yapı | Teklif Sistemi",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* Karanlık modu devre dışı bırakıp açık (beyaz) temayı sabitle */
    :root {
        color-scheme: light !important;
    }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
        color-scheme: light !important;
    }
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }

    /* Üst Streamlit header çubuğunu ve renkli çizgisini gizle */
    header[data-testid="stHeader"] {
        display: none !important;
        height: 0px !important;
    }
    div[data-testid="stDecoration"] {
        display: none !important;
    }
    div[data-testid="stToolbar"] {
        display: none !important;
    }

    /* İçeriğin en üstten rahat başlaması için boşluk ayarı */
    .block-container {
        padding-top: 2.2rem !important;
        padding-bottom: 2rem;
        max-width: 1150px;
    }
    .kpi-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        text-align: center;
    }
    .kpi-title {
        font-size: 0.80rem;
        color: #64748b;
        font-weight: 600;
        text-transform: uppercase;
    }
    .kpi-value {
        font-size: 1.45rem;
        color: #0f172a;
        font-weight: 700;
        margin-top: 4px;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        min-height: 42px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. LOGO İŞLEME (SİYAH ARKA PLANI ŞEFFAF PNG YAPAR)
# ---------------------------------------------------------
@st.cache_data
def hazirla_seffaf_logo():
    kaynak = None
    for aday in ["sayarlogopng.jpg", "logo.png", "sayarlogo.png", "logo.jpg"]:
        if os.path.exists(aday):
            kaynak = aday
            break
    if not kaynak:
        return None

    cikti = "logo_temiz.png"
    img = Image.open(kaynak).convert("RGBA")

    # Çok büyük görsellerde bellek ve hız için genişliği en fazla 800px yap
    max_genislik = 800
    if img.width > max_genislik:
        yeni_yukseklik = int(img.height * (max_genislik / img.width))
        img = img.resize((max_genislik, yeni_yukseklik), Image.Resampling.LANCZOS)

    try:
        import numpy as np
        arr = np.array(img, dtype=np.uint8)
        siyah_maske = (arr[:, :, 0] < 25) & (arr[:, :, 1] < 25) & (arr[:, :, 2] < 25)
        arr[siyah_maske] = [255, 255, 255, 0]
        img = Image.fromarray(arr, mode="RGBA")
    except ImportError:
        veriler = img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()
        yeni_veri = [
            (255, 255, 255, 0) if (r < 25 and g < 25 and b < 25) else (r, g, b, a)
            for r, g, b, a in veriler
        ]
        img.putdata(yeni_veri)

    img.save(cikti, "PNG", optimize=True)
    return cikti

# ---------------------------------------------------------
# 3. VERİTABANI YÖNETİMİ (SQLite - TEKLİFLER, ÜRÜNLER & YETKİLİLER)
# ---------------------------------------------------------
os.makedirs("/data", exist_ok=True)
DB_PATH = "/data/sayar_teklifler.db"

BASLANGIC_URUNLERI = [
    ("ALÇIMATİK 35 KG. (ALÇI ESASLI MAK. SIVASI)", "ENTEGRE", "İSTANBUL", "HARİÇ", "TORBA", 0.0),
    ("SIVAMATİK İÇ 50 KG. (ÇİM. ESAS. İÇ CEP. MAK. SIV.)", "ENTEGRE", "İSTANBUL", "HARİÇ", "TORBA", 0.0),
    ("SIVAMATİK DIŞ 50 KG. (ÇİM. ESAS. DIŞ CEP. MAK. SIV.)", "ENTEGRE", "İSTANBUL", "HARİÇ", "TORBA", 0.0),
    ("PRİMİEL 600 12 KG. (ADERANS ART. SEN. REÇ.)", "ENTEGRE", "İSTANBUL", "HARİÇ", "KOVA", 0.0),
    ("BAKLAVA KÖŞE (BOY: 2,70 MT.)", "ENTEGRE", "İSTANBUL", "HARİÇ", "BOY", 0.0),
    ("ÇELİK DÜBEL", "-", "İSTANBUL", "HARİÇ", "ADET", 0.0),
    ("TURUNCU PAKET YAPIŞTIRMA HARCI 25 KG.", "ENTEGRE", "İSTANBUL", "DAHİL", "TORBA", 0.0),
    ("TURUNCU PAKET DONATI SIVASI 25 KG.", "ENTEGRE", "İSTANBUL", "DAHİL", "TORBA", 0.0),
    ("TURUNCU PAKET DEKORATİF KAPLAMA SIV. 25 KG.", "ENTEGRE", "İSTANBUL", "DAHİL", "TORBA", 0.0),
    ("FİLELİ KÖŞE (BOY: 2,50 MT.)", "-", "İSTANBUL", "HARİÇ", "BOY", 0.0),
    ("FAWORİ DONATI FİLESİ 160 GR. (1 RULO: 55 MT.)", "FAWORİ", "İSTANBUL", "DAHİL", "RULO", 0.0),
    ("PREMİUM F 150 - 5 CM TAŞYÜNÜ", "BONUS", "İSTANBUL", "DAHİL", "M2", 0.0),
]

BASLANGIC_YETKILILERI = [
    ("YUSUF İSLAM SAYAR", "FİRMA YETKİLİSİ", "", ""),
    ("ABDULKERİM SAYAR", "FİRMA YETKİLİSİ", "", ""),
    ("ABDULHAKİM SAYAR", "FİRMA YETKİLİSİ", "", ""),
    ("ABDURRAHİM SAYAR", "FİRMA YETKİLİSİ", "", ""),
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS teklifler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belge_no TEXT UNIQUE,
            tarih TEXT,
            firma_adi TEXT,
            yetkili_kisi TEXT,
            telefon TEXT,
            santiye TEXT,
            odeme_tipi TEXT,
            vade_gun INTEGER,
            cekim_suresi TEXT,
            teslim_suresi TEXT,
            yetkili_personel TEXT,
            satis_sartlari TEXT,
            ara_toplam REAL,
            kdv_oran REAL,
            kdv_tutar REAL,
            genel_toplam REAL,
            durum TEXT DEFAULT 'Beklemede',
            kalemler_json TEXT,
            olusturma_zamani TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS urunler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            malzeme_adi TEXT UNIQUE,
            marka TEXT,
            fabrika TEXT,
            nakliye TEXT,
            birim TEXT,
            fiyat REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS satici_yetkilileri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_soyad TEXT UNIQUE,
            unvan TEXT,
            telefon TEXT,
            eposta TEXT
        )
    """)

    c.execute("SELECT COUNT(*) FROM urunler")
    if c.fetchone()[0] == 0:
        c.executemany("""
            INSERT OR IGNORE INTO urunler (malzeme_adi, marka, fabrika, nakliye, birim, fiyat)
            VALUES (?, ?, ?, ?, ?, ?)
        """, BASLANGIC_URUNLERI)

    c.execute("SELECT COUNT(*) FROM satici_yetkilileri")
    if c.fetchone()[0] == 0:
        c.executemany("""
            INSERT OR IGNORE INTO satici_yetkilileri (ad_soyad, unvan, telefon, eposta)
            VALUES (?, ?, ?, ?)
        """, BASLANGIC_YETKILILERI)

    conn.commit()
    conn.close()

def urunleri_getir():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM urunler ORDER BY malzeme_adi ASC", conn)
    conn.close()
    return df

def urun_kaydet_veya_guncelle(malzeme_adi, marka, fabrika, nakliye, birim, fiyat):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO urunler (malzeme_adi, marka, fabrika, nakliye, birim, fiyat)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(malzeme_adi) DO UPDATE SET
            marka=excluded.marka,
            fabrika=excluded.fabrika,
            nakliye=excluded.nakliye,
            birim=excluded.birim,
            fiyat=excluded.fiyat
    """, (
        malzeme_adi.strip().upper(),
        marka.strip().upper() or "-",
        fabrika.strip().upper() or "İSTANBUL",
        nakliye.strip().upper(),
        birim.strip().upper(),
        float(fiyat)
    ))
    conn.commit()
    conn.close()

def yetkilileri_getir():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM satici_yetkilileri ORDER BY id ASC", conn)
    conn.close()
    return df

def yetkili_ekle(ad_soyad, unvan, telefon, eposta):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO satici_yetkilileri (ad_soyad, unvan, telefon, eposta)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ad_soyad) DO UPDATE SET
            unvan=excluded.unvan,
            telefon=excluded.telefon,
            eposta=excluded.eposta
    """, (
        ad_soyad.strip().upper(),
        (unvan.strip().upper() or "FİRMA YETKİLİSİ"),
        telefon.strip(),
        eposta.strip()
    ))
    conn.commit()
    conn.close()

def yetkili_guncelle(yetkili_id, ad_soyad, unvan, telefon, eposta):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE satici_yetkilileri
        SET ad_soyad = ?, unvan = ?, telefon = ?, eposta = ?
        WHERE id = ?
    """, (
        ad_soyad.strip().upper(),
        (unvan.strip().upper() or "FİRMA YETKİLİSİ"),
        telefon.strip(),
        eposta.strip(),
        int(yetkili_id)
    ))
    conn.commit()
    conn.close()

def yetkili_sil(yetkili_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM satici_yetkilileri WHERE id = ?", (int(yetkili_id),))
    conn.commit()
    conn.close()

def teklif_sil(teklif_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM teklifler WHERE id = ?", (int(teklif_id),))
    conn.commit()
    conn.close()

def sonraki_belge_no():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM teklifler")
    sayi = c.fetchone()[0]
    conn.close()
    return f"TKLF-{datetime.now().year}-{sayi:04d}"

init_db()

# ---------------------------------------------------------
# 4. KURUMSAL PDF OLUŞTURMA MOTORU (LOGOLU)
# ---------------------------------------------------------
def turkce_temizle(text):
    if not text:
        return ""
    tr_map = str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")
    return str(text).translate(tr_map)

def get_pdf_font():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_paths = [
        os.path.join(base_dir, "DejaVuSans.ttf"),
        "DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    bold_paths = [
        os.path.join(base_dir, "DejaVuSans-Bold.ttf"),
        "DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for fp, bp in zip(font_paths, bold_paths):
        if os.path.exists(fp) and os.path.exists(bp):
            pdfmetrics.registerFont(TTFont("TRFont", fp))
            pdfmetrics.registerFont(TTFont("TRFont-Bold", bp))
            return "TRFont", "TRFont-Bold", True
    return "Helvetica", "Helvetica-Bold", False

def pdf_olustur(teklif_data):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_reg, font_bold, has_tr = get_pdf_font()

    def txt(val):
        return str(val) if has_tr else turkce_temizle(val)

    # Üst Kurumsal Antet (Açık Zemin + Mavi Vurgu Çizgisi)
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(30, height - 98, width - 60, 68, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#1d4ed8"))
    c.setLineWidth(2)
    c.line(30, height - 98, width - 30, height - 98)

    logo_yolu = hazirla_seffaf_logo()
    if logo_yolu and os.path.exists(logo_yolu):
        c.drawImage(logo_yolu, 38, height - 86, width=185, height=44, preserveAspectRatio=True, mask='auto')

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(font_bold, 10.5)
    c.drawRightString(width - 38, height - 48, txt("SAYAR YAPI ve İNŞAAT MALZEMELERİ"))
    c.setFont(font_reg, 8)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawRightString(width - 38, height - 60, txt("Gıda Oto. San. ve İç ve Dış Tic. Ltd. Şti."))
    c.drawRightString(width - 38, height - 71, txt("Alibeyköy Mah. Sevinç Cad. No:25 Eyüp / İSTANBUL"))
    c.drawRightString(width - 38, height - 82, txt("Tel: 0 (212) 625 25 52 | Web: sayaryapi.com.tr"))

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(font_bold, 13)
    c.drawCentredString(width / 2, height - 122, txt("TEKLİF MEKTUBU & SATIŞ SÖZLEŞMESİ"))

    # Müşteri ve Belge Bilgileri (Başlık altı boşluğu artırıldı)
    y = height - 154
    c.setFont(font_bold, 8.5)
    c.drawString(35, y, txt("FİRMA ADI:"))
    c.setFont(font_reg, 8.5)
    c.drawString(115, y, txt(teklif_data["firma_adi"]))

    c.setFont(font_bold, 8.5)
    c.drawString(380, y, txt("TARİH:"))
    c.setFont(font_reg, 8.5)
    c.drawString(450, y, txt(teklif_data["tarih"]))

    y -= 16
    c.setFont(font_bold, 8.5)
    c.drawString(35, y, txt("YETKİLİ KİŞİ:"))
    c.setFont(font_reg, 8.5)
    c.drawString(115, y, txt(teklif_data["yetkili_kisi"]))

    c.setFont(font_bold, 8.5)
    c.drawString(380, y, txt("BELGE NO:"))
    c.setFont(font_reg, 8.5)
    c.drawString(450, y, txt(teklif_data["belge_no"]))

    y -= 16
    c.setFont(font_bold, 8.5)
    c.drawString(35, y, txt("TELEFON NO:"))
    c.setFont(font_reg, 8.5)
    c.drawString(115, y, txt(teklif_data["telefon"]))

    c.setFont(font_bold, 8.5)
    c.drawString(380, y, txt("ŞANTİYE / YER:"))
    c.setFont(font_reg, 8.5)
    c.drawString(450, y, txt(teklif_data["santiye"]))

    # Malzeme Tablosu
    tablo_baslik = [
        txt("NO"), txt("MALZEMENİN İSMİ"), txt("MARKA"),
        txt("NAKLİYE"), txt("BİRİM"), txt("MİKTAR"), txt("FİYAT"), txt("TUTAR")
    ]
    tablo_verisi = [tablo_baslik]

    for idx, item in enumerate(teklif_data["kalemler"], start=1):
        tablo_verisi.append([
            str(idx),
            txt(item["malzeme"][:42]),
            txt(item["marka"]),
            txt(item["nakliye"]),
            txt(item["birim"]),
            f"{item['miktar']:,.2f}",
            f"{item['fiyat']:,.2f} ₺",
            f"{item['tutar']:,.2f} ₺"
        ])

    col_widths = [24, 200, 55, 50, 42, 48, 56, 60]
    table = Table(tablo_verisi, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), font_reg),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    # Tablo üst boşluğu artırıldı
    table_w, table_h = table.wrapOn(c, width, height)
    table_y = y - 30 - table_h
    table.drawOn(c, 30, table_y)

    # Alt Toplamlar (Tablo alt boşluğu artırıldı)
    alt_y = table_y - 34
    c.setFont(font_bold, 8.5)
    c.drawRightString(495, alt_y, txt("ARA TOPLAM:"))
    c.setFont(font_reg, 8.5)
    c.drawRightString(565, alt_y, f"{teklif_data['ara_toplam']:,.2f} TL")

    alt_y -= 14
    c.setFont(font_bold, 8.5)
    c.drawRightString(495, alt_y, txt(f"KDV (%{int(teklif_data['kdv_oran'])}):"))
    c.setFont(font_reg, 8.5)
    c.drawRightString(565, alt_y, f"{teklif_data['kdv_tutar']:,.2f} TL")

    alt_y -= 16
    c.setFillColor(colors.HexColor("#dc2626"))
    c.setFont(font_bold, 9.5)
    c.drawRightString(495, alt_y, txt("GENEL TOPLAM:"))
    c.drawRightString(565, alt_y, f"{teklif_data['genel_toplam']:,.2f} TL")
    c.setFillColor(colors.black)

    # Satış ve Ödeme Şartları (Tablo alt boşluğu artırıldı)
    sart_y = table_y - 34
    c.setFont(font_bold, 8.5)
    c.drawString(35, sart_y, txt("SATIŞ & ÖDEME ŞARTLARI:"))
    c.setFont(font_reg, 8)
    sart_y -= 13
    odeme_metni = f"Ödeme Şekli: {teklif_data['odeme_tipi']}"
    if teklif_data["odeme_tipi"] == "VADELİ":
        odeme_metni += f" ({teklif_data['vade_gun']} Gün)"
    c.drawString(35, sart_y, txt(f"* {odeme_metni}"))

    sart_y -= 12
    c.drawString(35, sart_y, txt(f"* Ürün Çekim Süresi: {teklif_data['cekim_suresi']} | Teslimat: {teklif_data['teslim_suresi']}"))

    for satir in teklif_data["satis_sartlari"].split("\n"):
        if satir.strip():
            sart_y -= 12
            c.drawString(35, sart_y, txt(f"* {satir.strip()}"))

    # İmza Alanları
    imza_y = max(sart_y - 45, 55)
    c.setFont(font_bold, 8.5)
    c.drawString(45, imza_y, txt("SATICI FİRMA YETKİLİSİ"))
    c.drawString(410, imza_y, txt("ALICI FİRMA ONAY / KAŞE"))

    c.setFont(font_reg, 8.5)
    c.drawString(45, imza_y - 14, txt(teklif_data["yetkili_personel"]))
    c.drawString(410, imza_y - 14, txt(teklif_data["firma_adi"][:30]))

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 5. OTURUM KONTROLÜ (LOGOLU GİRİŞ EKRANI)
# ---------------------------------------------------------
logo_ui = hazirla_seffaf_logo()

if "giris_yapildi" not in st.session_state:
    st.session_state.giris_yapildi = False

if not st.session_state.giris_yapildi:
    if logo_ui:
        st.image(logo_ui, width=260)
    st.markdown("### Fiyat Teklif & Ürün Yönetim Sistemi")
    sifre = st.text_input("Sistem Giriş Şifresi", type="password", placeholder="Şifrenizi girin...")
    if st.button("Giriş Yap", type="primary"):
        if sifre == "sayar2026":
            st.session_state.giris_yapildi = True
            st.rerun()
        else:
            st.error("Hatalı şifre.")
    st.stop()

# ---------------------------------------------------------
# 6. ANA ARAYÜZ SEKMELERİ (LOGOLU ÜST BAŞLIK)
# ---------------------------------------------------------
col_logo, col_baslik = st.columns([1.2, 3], vertical_alignment="center")
if logo_ui:
    col_logo.image(logo_ui, width=200)
col_baslik.markdown("<h2 style='margin:0; padding:0; line-height:1.25;'>Dijital Teklif & Ürün Yönetim Sistemi</h2>", unsafe_allow_html=True)

tab_yeni, tab_urunler, tab_yetkililer, tab_gecmis = st.tabs([
    "➕ Yeni Teklif Hazırla",
    "📦 Ürünler (Katalog)",
    "👤 Satıcı Firma Yetkilisi",
    "📂 Kayıtlı Teklifler"
])

BIRIM_LISTESI = ["TORBA", "KOVA", "RULO", "M2", "BOY", "ADET", "KG", "PALET", "SET", "MT"]
YENI_URUN_ETIKETI = "➕ YENİ ÜRÜN GİRİŞİ (ELLE YAZ)"

def malzeme_formunu_temizle():
    st.session_state.secilen_urun_box = YENI_URUN_ETIKETI
    st.session_state.son_secilen_urun = YENI_URUN_ETIKETI
    st.session_state.f_malzeme = ""
    st.session_state.f_marka = ""
    st.session_state.f_fabrika = "İSTANBUL"
    st.session_state.f_nakliye = "HARİÇ"
    st.session_state.f_birim = "TORBA"
    st.session_state.f_miktar = 1.0
    st.session_state.f_fiyat = 0.0

def teklif_formunu_sifirla():
    st.session_state.duzenlenen_teklif_id = None
    st.session_state.teklif_kalemleri = []
    st.session_state.t_firma = ""
    st.session_state.t_yetkili_kisi = ""
    st.session_state.t_belge_no = sonraki_belge_no()
    st.session_state.t_telefon = ""
    st.session_state.t_santiye = "ALİBEYKÖY / ŞANTİYE"
    st.session_state.t_tarih = date.today()
    st.session_state.t_odeme_tipi = "NAKİT"
    st.session_state.t_vade_gun = 0
    st.session_state.t_cekim_suresi = "60 GÜN ÇEKİM SÜRESİ"
    st.session_state.t_satis_sartlari = (
        "FİYATLARIMIZ KDV HARİÇTİR.\n"
        "TEKLİFİMİZ ONAYLANDIKTAN SONRA GEÇERLİLİK KAZANIR.\n"
        "TESLİMAT SÜRESİ SİPARİŞ ONAYINA MÜTEAKİP 3 İŞ GÜNÜDÜR."
    )
    st.session_state.t_kdv_oran = 20

# =========================================================
# SEKME 1: YENİ TEKLİF OLUŞTURMA / DÜZENLEME
# =========================================================
with tab_yeni:
    if "teklif_kalemleri" not in st.session_state:
        st.session_state.teklif_kalemleri = []
    if "duzenlenen_teklif_id" not in st.session_state:
        st.session_state.duzenlenen_teklif_id = None
    if "t_belge_no" not in st.session_state:
        st.session_state.t_belge_no = sonraki_belge_no()

    if st.session_state.pop("form_temizle_istegi", False):
        malzeme_formunu_temizle()

    if st.session_state.duzenlenen_teklif_id is not None:
        col_uyari, col_iptal = st.columns([3.5, 1])
        col_uyari.info(f"✏️ **{st.session_state.t_belge_no}** numaralı kayıtlı teklif düzenleniyor.")
        if col_iptal.button("Düzenlemeyi İptal Et", use_container_width=True):
            teklif_formunu_sifirla()
            st.rerun()

    with st.container(border=True):
        st.markdown("**1. Müşteri & Belge Bilgileri**")
        c1, c2, c3 = st.columns([2, 1.5, 1])
        firma_adi = c1.text_input("Firma Adı *", key="t_firma", placeholder="Örn: ABC İnşaat Ltd. Şti.")
        yetkili_kisi = c2.text_input("Yetkili Kişi", key="t_yetkili_kisi", placeholder="Örn: Ahmet Bey")
        belge_no = c3.text_input("Belge No", key="t_belge_no")

        c4, c5, c6 = st.columns([1.2, 1.8, 1])
        telefon = c4.text_input("Telefon No", key="t_telefon", placeholder="05XX XXX XX XX")
        santiye = c5.text_input("Şantiye / Teslim Yeri", key="t_santiye", value="ALİBEYKÖY / ŞANTİYE")
        tarih = c6.date_input("Teklif Tarihi", key="t_tarih", value=date.today())

    with st.container(border=True):
        st.markdown("**2. Malzeme Kalemi Ekle**")
        df_urunler = urunleri_getir()
        urun_secenekleri = [YENI_URUN_ETIKETI] + df_urunler["malzeme_adi"].tolist()

        if "secilen_urun_box" not in st.session_state or st.session_state.secilen_urun_box not in urun_secenekleri:
            st.session_state.secilen_urun_box = YENI_URUN_ETIKETI

        secilen_urun = st.selectbox(
            "Kayıtlı Ürünlerden Seçin veya Yeni Ürün Girin",
            urun_secenekleri,
            key="secilen_urun_box"
        )

        if "son_secilen_urun" not in st.session_state or st.session_state.son_secilen_urun != secilen_urun:
            st.session_state.son_secilen_urun = secilen_urun
            if secilen_urun == YENI_URUN_ETIKETI:
                st.session_state.f_malzeme = ""
                st.session_state.f_marka = ""
                st.session_state.f_fabrika = "İSTANBUL"
                st.session_state.f_nakliye = "HARİÇ"
                st.session_state.f_birim = "TORBA"
                st.session_state.f_miktar = 1.0
                st.session_state.f_fiyat = 0.0
            else:
                satir_u = df_urunler[df_urunler["malzeme_adi"] == secilen_urun].iloc[0]
                st.session_state.f_malzeme = satir_u["malzeme_adi"]
                st.session_state.f_marka = satir_u["marka"]
                st.session_state.f_fabrika = satir_u["fabrika"]
                st.session_state.f_nakliye = satir_u["nakliye"] if satir_u["nakliye"] in ["DAHİL", "HARİÇ"] else "HARİÇ"
                st.session_state.f_birim = satir_u["birim"] if satir_u["birim"] in BIRIM_LISTESI else "ADET"
                st.session_state.f_miktar = 1.0
                st.session_state.f_fiyat = float(satir_u["fiyat"] or 0.0)

        k1, k2, k3, k4 = st.columns([2.2, 1, 1, 1])
        malzeme_adi = k1.text_input("Malzeme Adı *", key="f_malzeme", placeholder="Yeni ürün adı yazın...")
        marka = k2.text_input("Marka", key="f_marka", placeholder="Örn: ENTEGRE")
        fabrika = k3.text_input("Fabrika", key="f_fabrika")
        nakliye = k4.selectbox("Nakliye", ["DAHİL", "HARİÇ"], key="f_nakliye")

        k5, k6, k7, k8 = st.columns([1, 1, 1.2, 1])
        birim = k5.selectbox("Birim", BIRIM_LISTESI, key="f_birim")
        miktar = k6.number_input("Miktar", min_value=0.0, step=1.0, key="f_miktar")
        fiyat = k7.number_input("Birim Fiyat (KDV Hariç ₺)", min_value=0.0, step=0.5, key="f_fiyat")

        k8.write("")
        k8.write("")
        if k8.button("➕ Satıra Ekle", use_container_width=True):
            temiz_ad = malzeme_adi.strip().upper()
            if temiz_ad and miktar > 0:
                st.session_state.teklif_kalemleri.append({
                    "malzeme": temiz_ad,
                    "marka": (marka.strip().upper() or "-"),
                    "fabrika": (fabrika.strip().upper() or "İSTANBUL"),
                    "nakliye": nakliye,
                    "birim": birim,
                    "miktar": float(miktar),
                    "fiyat": float(fiyat),
                    "tutar": round(float(miktar) * float(fiyat), 2)
                })

                mevcut_isimler = set(df_urunler["malzeme_adi"].str.upper().tolist())
                if secilen_urun == YENI_URUN_ETIKETI or temiz_ad not in mevcut_isimler:
                    urun_kaydet_veya_guncelle(temiz_ad, marka, fabrika, nakliye, birim, fiyat)
                    st.toast(f"'{temiz_ad}' Ürünler kataloğuna da kaydedildi!", icon="📦")

                st.session_state.form_temizle_istegi = True
                st.rerun()
            else:
                st.warning("Lütfen malzeme adı ve miktar girin.")

    # Eklenen Kalemler Tablosu
    if st.session_state.teklif_kalemleri:
        st.markdown("**Teklif Kalemleri (Tablo Üzerinden Miktar/Fiyat Düzenleyebilirsiniz)**")
        df_kalem = pd.DataFrame(st.session_state.teklif_kalemleri)
        edited_df = st.data_editor(
            df_kalem,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "malzeme": "Malzeme İsmi",
                "marka": "Marka",
                "fabrika": "Fabrika",
                "nakliye": "Nakliye",
                "birim": "Birim",
                "miktar": st.column_config.NumberColumn("Miktar", format="%.2f"),
                "fiyat": st.column_config.NumberColumn("Birim Fiyat (₺)", format="%.2f"),
                "tutar": st.column_config.NumberColumn("Tutar (₺)", disabled=True, format="%.2f"),
            }
        )
        guncel_kalemler = []
        for _, row in edited_df.iterrows():
            if pd.notna(row["malzeme"]) and str(row["malzeme"]).strip():
                m = float(row["miktar"] or 0)
                f = float(row["fiyat"] or 0)
                guncel_kalemler.append({
                    "malzeme": str(row["malzeme"]),
                    "marka": str(row["marka"] or "-"),
                    "fabrika": str(row["fabrika"] or "İSTANBUL"),
                    "nakliye": str(row["nakliye"] or "HARİÇ"),
                    "birim": str(row["birim"] or "ADET"),
                    "miktar": m,
                    "fiyat": f,
                    "tutar": round(m * f, 2)
                })
        st.session_state.teklif_kalemleri = guncel_kalemler

        if st.button("🗑️ Tüm Satırları Temizle"):
            st.session_state.teklif_kalemleri = []
            st.rerun()

    # Ödeme & Satış Şartları
    df_yetkililer = yetkilileri_getir()
    yetkili_listesi = df_yetkililer["ad_soyad"].tolist() if not df_yetkililer.empty else ["YUSUF İSLAM SAYAR"]

    with st.container(border=True):
        st.markdown("**3. Ödeme, Teslimat ve Satış Şartları**")
        s1, s2, s3, s4 = st.columns([1, 1, 1.2, 1.5])
        odeme_tipi = s1.selectbox("Ödeme Şekli", ["NAKİT", "VADELİ"], key="t_odeme_tipi")
        vade_gun = s2.number_input("Vade (Gün)", min_value=0, key="t_vade_gun", step=15)
        cekim_suresi = s3.text_input("Ürün Çekim Süresi", key="t_cekim_suresi", value="60 GÜN ÇEKİM SÜRESİ")
        yetkili_personel = s4.selectbox("Satıcı Firma Yetkilisi", yetkili_listesi, key="t_yetkili_personel")

        col_sart, col_ozet = st.columns([1.6, 1])
        satis_sartlari = col_sart.text_area(
            "Satış Şartları Maddeleri",
            key="t_satis_sartlari",
            value=(
                "FİYATLARIMIZ KDV HARİÇTİR.\n"
                "TEKLİFİMİZ ONAYLANDIKTAN SONRA GEÇERLİLİK KAZANIR.\n"
                "TESLİMAT SÜRESİ SİPARİŞ ONAYINA MÜTEAKİP 3 İŞ GÜNÜDÜR."
            ),
            height=105
        )
        kdv_oran = col_ozet.number_input("KDV Oranı (%)", min_value=0, max_value=30, key="t_kdv_oran", value=20)

        ara_toplam = sum(k["tutar"] for k in st.session_state.teklif_kalemleri)
        kdv_tutar = round(ara_toplam * (kdv_oran / 100.0), 2)
        genel_toplam = round(ara_toplam + kdv_tutar, 2)

        col_ozet.markdown(f"""
- **Ara Toplam:** `{ara_toplam:,.2f} ₺`
- **KDV (%{kdv_oran}):** `{kdv_tutar:,.2f} ₺`
- **GENEL TOPLAM:** **`{genel_toplam:,.2f} ₺`**
        """)

    kaydet_etiketi = "💾 Değişiklikleri Kaydet ve PDF Hazırla" if st.session_state.duzenlenen_teklif_id else "💾 Teklifi Kaydet ve PDF Hazırla"
    if st.button(kaydet_etiketi, type="primary", use_container_width=True):
        if not firma_adi.strip():
            st.error("Lütfen Firma Adı giriniz.")
        elif not st.session_state.teklif_kalemleri:
            st.error("Lütfen en az 1 malzeme satırı ekleyiniz.")
        else:
            teklif_obj = {
                "belge_no": belge_no.strip(),
                "tarih": tarih.strftime("%d.%m.%Y"),
                "firma_adi": firma_adi.strip().upper(),
                "yetkili_kisi": yetkili_kisi.strip().upper(),
                "telefon": telefon.strip(),
                "santiye": santiye.strip().upper(),
                "odeme_tipi": odeme_tipi,
                "vade_gun": int(vade_gun),
                "cekim_suresi": cekim_suresi.strip().upper(),
                "teslim_suresi": "3 İŞ GÜNÜ",
                "yetkili_personel": yetkili_personel,
                "satis_sartlari": satis_sartlari.strip().upper(),
                "ara_toplam": ara_toplam,
                "kdv_oran": float(kdv_oran),
                "kdv_tutar": kdv_tutar,
                "genel_toplam": genel_toplam,
                "kalemler": st.session_state.teklif_kalemleri
            }

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            if st.session_state.duzenlenen_teklif_id is not None:
                c.execute("""
                    UPDATE teklifler SET
                        belge_no = ?, tarih = ?, firma_adi = ?, yetkili_kisi = ?, telefon = ?,
                        santiye = ?, odeme_tipi = ?, vade_gun = ?, cekim_suresi = ?,
                        teslim_suresi = ?, yetkili_personel = ?, satis_sartlari = ?,
                        ara_toplam = ?, kdv_oran = ?, kdv_tutar = ?, genel_toplam = ?,
                        kalemler_json = ?
                    WHERE id = ?
                """, (
                    teklif_obj["belge_no"], teklif_obj["tarih"], teklif_obj["firma_adi"],
                    teklif_obj["yetkili_kisi"], teklif_obj["telefon"], teklif_obj["santiye"],
                    teklif_obj["odeme_tipi"], teklif_obj["vade_gun"], teklif_obj["cekim_suresi"],
                    teklif_obj["teslim_suresi"], teklif_obj["yetkili_personel"],
                    teklif_obj["satis_sartlari"], teklif_obj["ara_toplam"], teklif_obj["kdv_oran"],
                    teklif_obj["kdv_tutar"], teklif_obj["genel_toplam"],
                    json.dumps(teklif_obj["kalemler"], ensure_ascii=False),
                    int(st.session_state.duzenlenen_teklif_id)
                ))
                st.session_state.duzenlenen_teklif_id = None
            else:
                c.execute("""
                    INSERT OR REPLACE INTO teklifler (
                        belge_no, tarih, firma_adi, yetkili_kisi, telefon, santiye,
                        odeme_tipi, vade_gun, cekim_suresi, teslim_suresi, yetkili_personel,
                        satis_sartlari, ara_toplam, kdv_oran, kdv_tutar, genel_toplam,
                        durum, kalemler_json, olusturma_zamani
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Beklemede', ?, ?)
                """, (
                    teklif_obj["belge_no"], teklif_obj["tarih"], teklif_obj["firma_adi"],
                    teklif_obj["yetkili_kisi"], teklif_obj["telefon"], teklif_obj["santiye"],
                    teklif_obj["odeme_tipi"], teklif_obj["vade_gun"], teklif_obj["cekim_suresi"],
                    teklif_obj["teslim_suresi"], teklif_obj["yetkili_personel"],
                    teklif_obj["satis_sartlari"], teklif_obj["ara_toplam"], teklif_obj["kdv_oran"],
                    teklif_obj["kdv_tutar"], teklif_obj["genel_toplam"],
                    json.dumps(teklif_obj["kalemler"], ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            conn.commit()
            conn.close()

            st.success(f"✅ {teklif_obj['belge_no']} numaralı teklif kaydedildi!")
            pdf_buf = pdf_olustur(teklif_obj)
            st.download_button(
                label="📥 Kurumsal PDF Teklif Formunu İndir",
                data=pdf_buf,
                file_name=f"{teklif_obj['belge_no']}_{teklif_obj['firma_adi'][:20]}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# =========================================================
# SEKME 2: ÜRÜNLER KATALOĞU
# =========================================================
with tab_urunler:
    st.markdown("**Kayıtlı Ürün Listesi ve Fiyat Yönetimi**")
    st.caption("Buradan yeni ürün ekleyebilir veya tablodaki ürünlerin fiyat, marka, fabrika ve nakliye bilgilerini doğrudan düzenleyip kaydedebilirsiniz.")

    with st.expander("➕ Kataloğa Yeni Ürün Ekle", expanded=False):
        u1, u2, u3 = st.columns([2.2, 1, 1])
        y_ad = u1.text_input("Malzeme Adı *", key="kat_ad")
        y_marka = u2.text_input("Marka", value="ENTEGRE", key="kat_marka")
        y_fabrika = u3.text_input("Fabrika", value="İSTANBUL", key="kat_fabrika")

        u4, u5, u6, u7 = st.columns([1, 1, 1.2, 1])
        y_nakliye = u4.selectbox("Nakliye", ["DAHİL", "HARİÇ"], key="kat_nakliye")
        y_birim = u5.selectbox("Birim", BIRIM_LISTESI, key="kat_birim")
        y_fiyat = u6.number_input("Birim Fiyat (₺)", min_value=0.0, step=0.5, key="kat_fiyat")

        u7.write("")
        u7.write("")
        if u7.button("Kaydet", type="primary", use_container_width=True, key="kat_kaydet"):
            if y_ad.strip():
                urun_kaydet_veya_guncelle(y_ad, y_marka, y_fabrika, y_nakliye, y_birim, y_fiyat)
                st.success(f"✅ '{y_ad.strip().upper()}' ürün kataloğuna eklendi.")
                st.rerun()
            else:
                st.warning("Lütfen Malzeme Adı giriniz.")

    df_kat = urunleri_getir()
    urun_arama = st.text_input("🔍 Ürün Ara", placeholder="Malzeme adı veya marka yazın...", key="urun_ara")
    if urun_arama:
        df_kat_goster = df_kat[
            df_kat["malzeme_adi"].str.contains(urun_arama, case=False, na=False) |
            df_kat["marka"].str.contains(urun_arama, case=False, na=False)
        ].copy()
    else:
        df_kat_goster = df_kat.copy()

    edited_urunler = st.data_editor(
        df_kat_goster,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "malzeme_adi": st.column_config.TextColumn("Malzeme Adı", required=True),
            "marka": st.column_config.TextColumn("Marka"),
            "fabrika": st.column_config.TextColumn("Fabrika"),
            "nakliye": st.column_config.SelectboxColumn("Nakliye", options=["DAHİL", "HARİÇ"]),
            "birim": st.column_config.SelectboxColumn("Birim", options=BIRIM_LISTESI),
            "fiyat": st.column_config.NumberColumn("Güncel Fiyat (₺)", min_value=0.0, format="%.2f"),
        },
        key="urun_editor"
    )

    if st.button("💾 Katalog Değişikliklerini Kaydet", type="primary"):
        if not urun_arama:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM urunler")
            for _, r in edited_urunler.iterrows():
                if pd.notna(r["malzeme_adi"]) and str(r["malzeme_adi"]).strip():
                    c.execute("""
                        INSERT OR REPLACE INTO urunler (malzeme_adi, marka, fabrika, nakliye, birim, fiyat)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        str(r["malzeme_adi"]).strip().upper(),
                        str(r["marka"] or "-").strip().upper(),
                        str(r["fabrika"] or "İSTANBUL").strip().upper(),
                        str(r["nakliye"] or "HARİÇ").strip().upper(),
                        str(r["birim"] or "ADET").strip().upper(),
                        float(r["fiyat"] or 0.0)
                    ))
            conn.commit()
            conn.close()
            st.success("✅ Ürün kataloğu güncellendi!")
            st.rerun()
        else:
            for _, r in edited_urunler.iterrows():
                if pd.notna(r["malzeme_adi"]) and str(r["malzeme_adi"]).strip():
                    urun_kaydet_veya_guncelle(
                        str(r["malzeme_adi"]),
                        str(r["marka"] or "-"),
                        str(r["fabrika"] or "İSTANBUL"),
                        str(r["nakliye"] or "HARİÇ"),
                        str(r["birim"] or "ADET"),
                        float(r["fiyat"] or 0.0)
                    )
            st.success("✅ Filtrelenen ürünlerin değişiklikleri kaydedildi!")
            st.rerun()

# =========================================================
# SEKME 3: SATICI FİRMA YETKİLİSİ YÖNETİMİ
# =========================================================
with tab_yetkililer:
    st.markdown("**Satıcı Firma Yetkilileri**")
    st.caption("Yeni yetkili ekleyebilir, mevcut yetkili bilgilerini düzenleyebilir veya silebilirsiniz.")

    with st.expander("➕ Yeni Satıcı Firma Yetkilisi Ekle", expanded=False):
        y1, y2, y3, y4 = st.columns([1.8, 1.4, 1.2, 1.4])
        y_ad_soyad = y1.text_input("Ad Soyad *", key="yet_yeni_ad", placeholder="Örn: MEHMET SAYAR")
        y_unvan = y2.text_input("Unvan", value="FİRMA YETKİLİSİ", key="yet_yeni_unvan")
        y_tel = y3.text_input("Telefon", key="yet_yeni_tel", placeholder="05XX XXX XX XX")
        y_mail = y4.text_input("E-posta", key="yet_yeni_mail", placeholder="ornek@sayaryapi.com.tr")

        if st.button("Yetkili Kaydet", type="primary", key="yet_yeni_kaydet"):
            if y_ad_soyad.strip():
                yetkili_ekle(y_ad_soyad, y_unvan, y_tel, y_mail)
                st.success(f"✅ '{y_ad_soyad.strip().upper()}' yetkili listesine eklendi.")
                st.rerun()
            else:
                st.warning("Lütfen Ad Soyad giriniz.")

    df_y_liste = yetkilileri_getir()
    if df_y_liste.empty:
        st.info("Henüz kayıtlı satıcı firma yetkilisi bulunmuyor.")
    else:
        for _, y_row in df_y_liste.iterrows():
            y_id = int(y_row["id"])
            with st.container(border=True):
                col_info, col_btn1, col_btn2 = st.columns([3.2, 0.9, 0.9])
                detay_parcalari = [f"📌 {y_row['unvan'] or 'FİRMA YETKİLİSİ'}"]
                if y_row["telefon"]:
                    detay_parcalari.append(f"📞 {y_row['telefon']}")
                if y_row["eposta"]:
                    detay_parcalari.append(f"✉️ {y_row['eposta']}")

                col_info.markdown(f"**{y_row['ad_soyad']}**")
                col_info.caption(" | ".join(detay_parcalari))

                duzenle_acik = st.session_state.get(f"yet_duzenle_{y_id}", False)
                if col_btn1.button("✏️ Düzenle", key=f"btn_yet_duz_{y_id}", use_container_width=True):
                    st.session_state[f"yet_duzenle_{y_id}"] = not duzenle_acik
                    st.rerun()

                if col_btn2.button("🗑️ Sil", key=f"btn_yet_sil_{y_id}", use_container_width=True):
                    yetkili_sil(y_id)
                    st.toast(f"'{y_row['ad_soyad']}' silindi.", icon="🗑️")
                    st.rerun()

                if st.session_state.get(f"yet_duzenle_{y_id}", False):
                    st.divider()
                    e1, e2, e3, e4 = st.columns([1.8, 1.4, 1.2, 1.4])
                    g_ad = e1.text_input("Ad Soyad", value=y_row["ad_soyad"], key=f"ed_yad_{y_id}")
                    g_unvan = e2.text_input("Unvan", value=y_row["unvan"] or "", key=f"ed_yunvan_{y_id}")
                    g_tel = e3.text_input("Telefon", value=y_row["telefon"] or "", key=f"ed_ytel_{y_id}")
                    g_mail = e4.text_input("E-posta", value=y_row["eposta"] or "", key=f"ed_ymail_{y_id}")

                    c_kay, c_vaz = st.columns([1, 1])
                    if c_kay.button("💾 Güncelle", type="primary", key=f"save_yet_{y_id}"):
                        if g_ad.strip():
                            yetkili_guncelle(y_id, g_ad, g_unvan, g_tel, g_mail)
                            st.session_state[f"yet_duzenle_{y_id}"] = False
                            st.success("✅ Yetkili bilgileri güncellendi.")
                            st.rerun()
                        else:
                            st.warning("Ad Soyad boş bırakılamaz.")
                    if c_vaz.button("Vazgeç", key=f"cancel_yet_{y_id}"):
                        st.session_state[f"yet_duzenle_{y_id}"] = False
                        st.rerun()

# =========================================================
# SEKME 4: KAYITLI TEKLİFLER VE TAKİP
# =========================================================
with tab_gecmis:
    conn = sqlite3.connect(DB_PATH)
    df_teklifler = pd.read_sql_query("SELECT * FROM teklifler ORDER BY id DESC", conn)
    conn.close()

    if df_teklifler.empty:
        st.info("Henüz kayıtlı teklif bulunmuyor.")
    else:
        toplam_sayi = len(df_teklifler)
        bekleyen_sayi = len(df_teklifler[df_teklifler["durum"] == "Beklemede"])
        onayli_tutar = df_teklifler[df_teklifler["durum"] == "Onaylandı"]["genel_toplam"].sum()

        k1, k2, k3 = st.columns(3)
        k1.markdown(f'<div class="kpi-card"><div class="kpi-title">Toplam Teklif</div><div class="kpi-value">{toplam_sayi}</div></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="kpi-card"><div class="kpi-title">Onay Bekleyen</div><div class="kpi-value">{bekleyen_sayi}</div></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="kpi-card"><div class="kpi-title">Onaylanan Ciro</div><div class="kpi-value">{onayli_tutar:,.0f} ₺</div></div>', unsafe_allow_html=True)

        st.write("")
        arama = st.text_input("🔍 Firma, Şantiye veya Belge No Ara", placeholder="Aramak için yazın...")
        if arama:
            mask = (
                df_teklifler["firma_adi"].str.contains(arama, case=False, na=False) |
                df_teklifler["santiye"].str.contains(arama, case=False, na=False) |
                df_teklifler["belge_no"].str.contains(arama, case=False, na=False)
            )
            df_teklifler = df_teklifler[mask]

        for _, row in df_teklifler.iterrows():
            t_id = int(row["id"])
            with st.container(border=True):
                c_sol, c_sag = st.columns([2.5, 1.2])
                c_sol.markdown(f"**{row['belge_no']}** | **{row['firma_adi']}** (`{row['durum']}`)")
                c_sol.caption(f"📍 Şantiye: {row['santiye']} | 📅 Tarih: {row['tarih']} | 👤 Yetkili: {row['yetkili_personel']}")
                c_sag.markdown(f"**Genel Toplam:** `{row['genel_toplam']:,.2f} ₺`")

                b1, b2, b3, b4 = st.columns([1.1, 0.9, 0.9, 1.3])
                yeni_durum = b1.selectbox(
                    "Durum",
                    ["Beklemede", "Onaylandı", "Revize", "İptal"],
                    index=["Beklemede", "Onaylandı", "Revize", "İptal"].index(row["durum"]),
                    key=f"durum_{t_id}",
                    label_visibility="collapsed"
                )
                if yeni_durum != row["durum"]:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE teklifler SET durum = ? WHERE id = ?", (yeni_durum, t_id))
                    conn.commit()
                    conn.close()
                    st.rerun()

                if b2.button("✏️ Düzenle", key=f"duz_teklif_{t_id}", use_container_width=True):
                    st.session_state.duzenlenen_teklif_id = t_id
                    st.session_state.t_firma = row["firma_adi"] or ""
                    st.session_state.t_yetkili_kisi = row["yetkili_kisi"] or ""
                    st.session_state.t_belge_no = row["belge_no"] or ""
                    st.session_state.t_telefon = row["telefon"] or ""
                    st.session_state.t_santiye = row["santiye"] or ""
                    try:
                        st.session_state.t_tarih = datetime.strptime(row["tarih"], "%d.%m.%Y").date()
                    except Exception:
                        st.session_state.t_tarih = date.today()
                    st.session_state.t_odeme_tipi = row["odeme_tipi"] if row["odeme_tipi"] in ["NAKİT", "VADELİ"] else "NAKİT"
                    st.session_state.t_vade_gun = int(row["vade_gun"] or 0)
                    st.session_state.t_cekim_suresi = row["cekim_suresi"] or "60 GÜN ÇEKİM SÜRESİ"
                    if row["yetkili_personel"] in yetkili_listesi:
                        st.session_state.t_yetkili_personel = row["yetkili_personel"]
                    st.session_state.t_satis_sartlari = row["satis_sartlari"] or ""
                    st.session_state.t_kdv_oran = int(row["kdv_oran"] or 20)
                    try:
                        st.session_state.teklif_kalemleri = json.loads(row["kalemler_json"] or "[]")
                    except Exception:
                        st.session_state.teklif_kalemleri = []
                    st.toast(f"{row['belge_no']} düzenlenmek üzere 'Yeni Teklif Hazırla' sekmesine yüklendi.", icon="✏️")
                    st.rerun()

                if b3.button("🗑️ Sil", key=f"sil_teklif_{t_id}", use_container_width=True):
                    teklif_sil(t_id)
                    st.toast(f"{row['belge_no']} silindi.", icon="🗑️")
                    st.rerun()

                teklif_dict = dict(row)
                teklif_dict["kalemler"] = json.loads(row["kalemler_json"])
                pdf_b = pdf_olustur(teklif_dict)
                b4.download_button(
                    "📥 PDF İndir",
                    data=pdf_b,
                    file_name=f"{row['belge_no']}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{t_id}",
                    use_container_width=True
                )
