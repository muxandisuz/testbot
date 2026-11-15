# 🎯 TestMaster Bot — Telegram Test Tizimi & Web Boshqaruv Paneli

**TestMaster Bot** — Aiogram 3.x + FastAPI + aiosqlite asosida yaratilgan zamonaviy, chiroyli va to'liq funksional Telegram test boti hamda brauzerda ishlaydigan **Jonli Simulyator + Admin Panel**.

## ✨ Asosiy Imkoniyatlar
- **Chiroyli Telegram In-Chat UI**: Inline tugmalar, Unicode progress-barlar (`▰▰▰▰▱▱▱▱▱▱`), daraja nishonlari (`🌱 Boshlovchi`, `⚡️ Bilimdon`, `🔥 Ekspert`, `👑 Grossmeyster`), HTML kartochkalar.
- **2 xil Test Rejimi**:
  - **⚡️ Mashq rejimi**: Har bir savoldan so'ng darhol to'g'ri/noto'g'ri holati va izoh ko'rsatiladi.
  - **🎓 Imtihon rejimi**: Taymer, savollar xaritasi (`📍/🔵/⚪️`), javobni o'zgartirish va vaqt tugaganda avtomatik yakunlash.
- **Kod orqali tezkor kirish**: `1001` – `1006` kabi test kodlarini yuborib darhol testga kirish.
- **Xatolar tahlili & Reyting**: Yakunlangan testdan keyin xatolarni birma-bir izoh bilan ko'rib chiqish, umumiy va fanlar bo'yicha Top-10 reyting.
- **Brauzerda Jonli Simulyator va Web Test Rejimi**: Telegram token kiritmasdan turib ham `http://127.0.0.1:8000` manzilida botni sinab ko'rish va test ishlash mumkin.
- **Admin Panel (Bot ichida `/admin` va Web UI)**: Fanlar, testlar yaratish, bittalab yoki ko'plab (`Savol | A | B | C | D | To'g'ri | Izoh`) savollarni import qilish.

## 🚀 Ishga tushirish

```powershell
# Virtual muhitni faollashtirish (yoki uv orqali)
.venv\Scripts\python.exe main.py
```

Keyin brauzerda oching: **http://127.0.0.1:8000**

Haqiqiy Telegram botga ulash uchun `.env` faylida `BOT_TOKEN` ni kiriting yoki Web UI dagi **🤖 Botni Ulash** bo'limidan tokenni saqlang.
