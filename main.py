import asyncio
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Optional

import httpx
import qrcode
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
VIP_LINK = os.getenv("VIP_LINK", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@suporte")
SUNIZE_API_KEY = os.getenv("SUNIZE_API_KEY", "")
SUNIZE_API_SECRET = os.getenv("SUNIZE_API_SECRET", "")
SUNIZE_BASE_URL = os.getenv("SUNIZE_BASE_URL", "https://api.sunize.com.br/v1").rstrip("/")
START_PHOTO_PATH = os.getenv("START_PHOTO_PATH", "media/start.jpg")
START_VIDEO_PATH = os.getenv("START_VIDEO_PATH", "media/start.mp4")

DEFAULT_CUSTOMER_NAME = os.getenv("DEFAULT_CUSTOMER_NAME", "Julia Costa")
DEFAULT_CUSTOMER_EMAIL = os.getenv("DEFAULT_CUSTOMER_EMAIL", "juliacosta@gmail.com")
DEFAULT_CUSTOMER_DOCUMENT = os.getenv("DEFAULT_CUSTOMER_DOCUMENT", "12345678910")
DEFAULT_CUSTOMER_PHONE = os.getenv("DEFAULT_CUSTOMER_PHONE", "")

PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///app.db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não configurado")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI(title="Telegram Bot Sunize")

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, index=True, nullable=False)
    username = Column(String, nullable=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    sunize_id = Column(String, nullable=True, index=True)
    has_call = Column(Boolean, default=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String, default="PENDING", index=True)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    customer_document = Column(String, nullable=True)
    pix_payload = Column(String, nullable=True)
    access_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


Base.metadata.create_all(bind=engine)


class Checkout(StatesGroup):
    waiting_name = State()
    waiting_email = State()
    waiting_phone = State()
    waiting_document = State()


def kb_age() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ 𝐒𝐨𝐮 𝐦𝐚𝐢𝐨𝐫 𝐝𝐞 𝟏𝟖 𝐚𝐧𝐨𝐬", callback_data="confirmar_18")
    ]])


def kb_buy() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥 𝐋𝐢𝐛𝐞𝐫𝐚𝐫 𝐦𝐞𝐮 𝐚𝐜𝐞𝐬𝐬𝐨 𝐚𝐠𝐨𝐫𝐚", callback_data="comprar_vitalicio")
    ]])


def kb_upsell() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😈 𝐀𝐝𝐢𝐜𝐢𝐨𝐧𝐚𝐫 𝐜𝐡𝐚𝐦𝐚𝐝𝐚 𝐝𝐞 𝟐𝟓 𝐦𝐢𝐧 — +𝐑$ 𝟏𝟓,𝟗𝟎", callback_data="upsell_sim")],
        [InlineKeyboardButton(text="❌ 𝐍𝐚̃𝐨, 𝐪𝐮𝐞𝐫𝐨 𝐬𝐨́ 𝐨 𝐚𝐜𝐞𝐬𝐬𝐨", callback_data="upsell_nao")],
    ])


def kb_pix(external_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 𝐉𝐚́ 𝐩𝐚𝐠𝐮𝐞𝐢, 𝐯𝐞𝐫𝐢𝐟𝐢𝐜𝐚𝐫", callback_data=f"verificar:{external_id}")],
        [InlineKeyboardButton(text="💬 𝐂𝐡𝐚𝐦𝐚𝐫 𝐬𝐮𝐩𝐨𝐫𝐭𝐞", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")],
    ])


def kb_access(has_call: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if VIP_LINK:
        rows.append([InlineKeyboardButton(text="🔞 𝐄𝐧𝐭𝐫𝐚𝐫 𝐧𝐨 𝐕𝐈𝐏 𝐩𝐫𝐢𝐯𝐚𝐝𝐨", url=VIP_LINK)])
    if has_call:
        rows.append([InlineKeyboardButton(text="📅 𝐀𝐠𝐞𝐧𝐝𝐚𝐫 𝐦𝐢𝐧𝐡𝐚 𝐜𝐡𝐚𝐦𝐚𝐝𝐚", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="💬 𝐂𝐡𝐚𝐦𝐚𝐫 𝐬𝐮𝐩𝐨𝐫𝐭𝐞", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")]])


START_TEXT = """🌸 𝐎𝐢𝐢, 𝐚𝐦𝐨𝐫... 𝐞𝐮 𝐞𝐬𝐭𝐚𝐯𝐚 𝐭𝐞 𝐞𝐬𝐩𝐞𝐫𝐚𝐧𝐝𝐨 💦💗

🔞 𝐀𝐂𝐄𝐒𝐒𝐎 𝐕𝐈𝐏 𝐏𝐑𝐈𝐕𝐀𝐃𝐎 🔞

+𝟖𝟐𝟎 𝐌𝐈́𝐃𝐈𝐀𝐒 𝐄𝐗𝐂𝐋𝐔𝐒𝐈𝐕𝐀𝐒 | 𝐏𝐑𝐈𝐕𝐀𝐂𝐘

😈 𝐀𝐍𝐀𝐋, 𝐁𝐎𝐐𝐔𝐄𝐓𝐄 𝐄 𝐂𝐎𝐍𝐓𝐄𝐔́𝐃𝐎 𝐏𝐑𝐎𝐈𝐁𝐈𝐃𝐈𝐍𝐇𝐎

🎀 Vídeos exclusivos bem safadinhos
🎀 Conteúdos íntimos que você não vê em qualquer lugar
🎀 Mídias novas e atualizações frequentes
🎀 Lives exclusivas para assinantes
🎀 Vídeo personalizado gemendo seu nome
🎀 Conteúdo privado, discreto e liberado na hora

🔞 𝐁𝐎̂𝐍𝐔𝐒 𝐄𝐗𝐂𝐋𝐔𝐒𝐈𝐕𝐎:

💗 WhatsApp pessoal
💗 +50 mídias extras proibidinhas
💗 Chamada de vídeo privada
💗 Vídeo personalizado gemendo seu nome
💗 Sorteios e surpresas especiais

💎 𝐀𝐜𝐞𝐬𝐬𝐨 𝐢𝐦𝐞𝐝𝐢𝐚𝐭𝐨
⭐ 𝟗𝟎 𝐝𝐢𝐚𝐬 𝐝𝐞 𝐠𝐚𝐫𝐚𝐧𝐭𝐢𝐚
🔒 𝐏𝐚𝐠𝐚𝐦𝐞𝐧𝐭𝐨 𝐝𝐢𝐬𝐜𝐫𝐞𝐭𝐨

💎 𝐀𝐂𝐄𝐒𝐒𝐎 𝐕𝐈𝐓𝐀𝐋𝐈́𝐂𝐈𝐎: 𝐑$ 𝟏𝟕,𝟒𝟗

😈 𝐓𝐚́ 𝐩𝐫𝐨𝐧𝐭𝐨 𝐩𝐫𝐚 𝐞𝐧𝐭𝐫𝐚𝐫 𝐧𝐨 𝐦𝐞𝐮 𝐩𝐫𝐢𝐯𝐚𝐝𝐨?

👇 𝐂𝐥𝐢𝐪𝐮𝐞 𝐚𝐛𝐚𝐢𝐱𝐨 𝐩𝐚𝐫𝐚 𝐜𝐨𝐧𝐭𝐢𝐧𝐮𝐚𝐫 👇"""


def normalize_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.startswith("+"):
        phone = "+55" + phone.lstrip("0")
    return phone


def only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def get_pix_payload(res: dict) -> str:
    pix = res.get("pix") or {}
    return (
        pix.get("payload")
        or pix.get("copy_paste")
        or pix.get("copyPaste")
        or pix.get("qrcode")
        or pix.get("qr_code")
        or res.get("pix_payload")
        or res.get("pixPayload")
        or ""
    )


def create_pix_qr_image(pix_payload: str, external_id: str) -> Optional[Path]:
    if not pix_payload:
        return None
    qr_dir = Path("/tmp/telegram_bot_qr")
    qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = qr_dir / f"pix_{external_id}.png"
    img = qrcode.make(pix_payload)
    img.save(qr_path)
    return qr_path


async def create_sunize_transaction(order: Order) -> dict:
    items = [{
        "id": "acesso_vitalicio",
        "title": "Acesso vitalício VIP",
        "description": "Plano vitalício",
        "price": 17.49,
        "quantity": 1,
        "is_physical": False,
    }]
    if order.has_call:
        items.append({
            "id": "chamada_25min",
            "title": "Chamada de vídeo 25 minutos",
            "description": "Oferta adicional",
            "price": 15.90,
            "quantity": 1,
            "is_physical": False,
        })

    payload = {
        "external_id": order.external_id,
        "total_amount": float(order.total_amount),
        "payment_method": "PIX",
        "items": items,
        "ip": "127.0.0.1",
        "customer": {
            "name": order.customer_name,
            "email": order.customer_email,
            "phone": order.customer_phone,
            "document_type": "CPF",
            "document": order.customer_document,
        },
    }

    headers = {"x-api-key": SUNIZE_API_KEY, "x-api-secret": SUNIZE_API_SECRET}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{SUNIZE_BASE_URL}/transactions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


async def send_access(telegram_id: str, has_call: bool) -> None:
    if has_call:
        text = """✅ 𝐏𝐚𝐠𝐚𝐦𝐞𝐧𝐭𝐨 𝐚𝐩𝐫𝐨𝐯𝐚𝐝𝐨

Seu acesso VIP vitalício foi liberado.

Você também garantiu a chamada de vídeo privada de 25 minutos.

Clique abaixo para entrar e agendar seu horário."""
    else:
        text = """✅ 𝐏𝐚𝐠𝐚𝐦𝐞𝐧𝐭𝐨 𝐚𝐩𝐫𝐨𝐯𝐚𝐝𝐨

Seu acesso VIP vitalício foi liberado.

Clique abaixo para entrar no privado."""
    await bot.send_message(int(telegram_id), text, reply_markup=kb_access(has_call))


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🔞 𝐂𝐨𝐧𝐭𝐞𝐮́𝐝𝐨 𝐩𝐚𝐫𝐚 𝐦𝐚𝐢𝐨𝐫𝐞𝐬 𝐝𝐞 𝟏𝟖 𝐚𝐧𝐨𝐬\n\n"
        "Para continuar, confirme sua idade abaixo:",
        reply_markup=kb_age(),
    )


@dp.callback_query(F.data == "confirmar_18")
async def confirmar_18(callback: types.CallbackQuery):
    photo_exists = Path(START_PHOTO_PATH).exists()
    video_exists = Path(START_VIDEO_PATH).exists()

    if photo_exists and video_exists:
        await callback.message.answer_media_group(media=[
            InputMediaPhoto(media=FSInputFile(START_PHOTO_PATH)),
            InputMediaVideo(media=FSInputFile(START_VIDEO_PATH)),
        ])
    elif photo_exists:
        await callback.message.answer_photo(FSInputFile(START_PHOTO_PATH))
    elif video_exists:
        await callback.message.answer_video(FSInputFile(START_VIDEO_PATH))
    else:
        if ADMIN_ID:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Mídia do /start não encontrada. Confira se existem: {START_PHOTO_PATH} e {START_VIDEO_PATH}"
            )

    await callback.message.answer(START_TEXT, reply_markup=kb_buy())
    await callback.answer()


@dp.callback_query(F.data == "comprar_vitalicio")
async def comprar(callback: types.CallbackQuery):
    text = """🔥 𝐎𝐟𝐞𝐫𝐭𝐚 𝐞𝐱𝐜𝐥𝐮𝐬𝐢𝐯𝐚

Antes de finalizar, você pode adicionar uma chamada de vídeo privada de 25 minutos por apenas 𝐑$ 𝟏𝟓,𝟗𝟎.

💎 Acesso vitalício: 𝐑$ 𝟏𝟕,𝟒𝟗
😈 Com chamada exclusiva: 𝐑$ 𝟑𝟑,𝟑𝟗

Quer deixar sua experiência mais completa?"""
    await callback.message.answer(text, reply_markup=kb_upsell())
    await callback.answer()


@dp.callback_query(F.data.in_({"upsell_sim", "upsell_nao"}))
async def upsell(callback: types.CallbackQuery, state: FSMContext):
    has_call = callback.data == "upsell_sim"
    await state.update_data(has_call=has_call)

    if DEFAULT_CUSTOMER_PHONE:
        await callback.message.answer("⏳ Gerando seu Pix, aguarde...")
        await gerar_pix(callback.message, callback.from_user, has_call, normalize_phone(DEFAULT_CUSTOMER_PHONE), state)
    else:
        await state.set_state(Checkout.waiting_phone)
        await callback.message.answer("Para gerar seu Pix, envie seu 𝐭𝐞𝐥𝐞𝐟𝐨𝐧𝐞 com DDD. Ex: 37999999999")

    await callback.answer()


@dp.message(Checkout.waiting_name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(Checkout.waiting_email)
    await message.answer("Agora envie seu 𝐞-𝐦𝐚𝐢𝐥:")


@dp.message(Checkout.waiting_email)
async def get_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer("E-mail inválido. Envie novamente:")
        return
    await state.update_data(customer_email=email)
    await state.set_state(Checkout.waiting_phone)
    await message.answer("Envie seu 𝐭𝐞𝐥𝐞𝐟𝐨𝐧𝐞 com DDD. Ex: 37999999999")


async def gerar_pix(message: types.Message, user: types.User, has_call: bool, phone: str, state: FSMContext):
    customer_document = only_digits(DEFAULT_CUSTOMER_DOCUMENT)
    if len(customer_document) != 11:
        await message.answer("❌ CPF padrão inválido. Ajuste DEFAULT_CUSTOMER_DOCUMENT no Railway.")
        await state.clear()
        return

    total = Decimal("33.39") if has_call else Decimal("17.49")
    external_id = f"tg_{user.id}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    order = Order(
        telegram_id=str(user.id),
        username=user.username,
        external_id=external_id,
        has_call=has_call,
        total_amount=total,
        customer_name=DEFAULT_CUSTOMER_NAME,
        customer_email=DEFAULT_CUSTOMER_EMAIL,
        customer_phone=phone,
        customer_document=customer_document,
    )

    db = SessionLocal()
    db.add(order)
    db.commit()
    db.refresh(order)

    try:
        res = await create_sunize_transaction(order)
        order.sunize_id = res.get("id")
        order.status = res.get("status", "PENDING")
        order.pix_payload = get_pix_payload(res)
        db.commit()
    except Exception as e:
        db.rollback()
        await message.answer("❌ Não consegui gerar o Pix agora. Chame o suporte ou tente novamente em alguns minutos.")
        if ADMIN_ID:
            await bot.send_message(ADMIN_ID, f"Erro ao gerar Pix: {e}")
        db.close()
        await state.clear()
        return

    db.close()
    await state.clear()

    valor = "33,39" if has_call else "17,49"
    resumo = f"""💳 𝐒𝐞𝐮 𝐏𝐢𝐱 𝐟𝐨𝐢 𝐠𝐞𝐫𝐚𝐝𝐨

Valor: 𝐑$ {valor}

Escaneie o QR Code ou copie o código Pix na próxima mensagem.

Após o pagamento, a liberação será automática."""
    await message.answer(resumo)

    pix_payload = order.pix_payload or "PIX não retornado pela Sunize"
    qr_path = create_pix_qr_image(order.pix_payload or "", external_id)
    if qr_path:
        await message.answer_photo(
            FSInputFile(qr_path),
            caption="📲 𝐐𝐑 𝐂𝐨𝐝𝐞 𝐏𝐢𝐱 — escaneie pelo app do banco."
        )

    codigo_msg = f"""📋 𝐂𝐨́𝐝𝐢𝐠𝐨 𝐏𝐢𝐱 𝐜𝐨𝐩𝐢𝐚 𝐞 𝐜𝐨𝐥𝐚

<code>{pix_payload}</code>"""
    await message.answer(codigo_msg, reply_markup=kb_pix(external_id), parse_mode="HTML")


@dp.message(Checkout.waiting_phone)
async def get_phone(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if len(only_digits(phone)) < 12:
        await message.answer("Telefone inválido. Envie com DDD. Ex: 37999999999")
        return

    data = await state.get_data()
    has_call = bool(data.get("has_call"))
    await message.answer("⏳ Gerando seu Pix, aguarde...")
    await gerar_pix(message, message.from_user, has_call, phone, state)


@dp.callback_query(F.data.startswith("verificar:"))
async def verificar(callback: types.CallbackQuery):
    external_id = callback.data.split(":", 1)[1]
    db = SessionLocal()
    order: Optional[Order] = db.execute(select(Order).where(Order.external_id == external_id)).scalar_one_or_none()
    if not order:
        db.close()
        await callback.message.answer("❌ Pedido não encontrado.")
        await callback.answer()
        return

    if order.status == "AUTHORIZED":
        if not order.access_sent:
            await send_access(order.telegram_id, order.has_call)
            order.access_sent = True
            db.commit()
        else:
            await callback.message.answer("✅ Seu acesso já foi liberado.", reply_markup=kb_access(order.has_call))
    else:
        await callback.message.answer("⏳ Pagamento ainda não identificado. Aguarde alguns instantes e tente verificar novamente.")
    db.close()
    await callback.answer()


@app.get("/")
async def root():
    return {"ok": True, "service": "telegram-sunize-bot"}


@app.post("/sunize/webhook")
async def sunize_webhook(request: Request):
    data = await request.json()
    external_id = data.get("external_id")
    status = data.get("status")

    if not external_id:
        return {"ok": False, "error": "external_id ausente"}

    db = SessionLocal()
    order: Optional[Order] = db.execute(select(Order).where(Order.external_id == external_id)).scalar_one_or_none()
    if not order:
        db.close()
        return {"ok": False, "error": "pedido não encontrado"}

    order.status = status or order.status
    if data.get("id") and not order.sunize_id:
        order.sunize_id = data.get("id")
    db.commit()

    should_send = order.status == "AUTHORIZED" and not order.access_sent
    telegram_id = order.telegram_id
    has_call = order.has_call

    if should_send:
        order.access_sent = True
        db.commit()
    db.close()

    if should_send:
        asyncio.create_task(send_access(telegram_id, has_call))
        if ADMIN_ID:
            asyncio.create_task(bot.send_message(ADMIN_ID, f"✅ Venda aprovada: R$ {data.get('total_amount')} | tg {telegram_id} | chamada={has_call}"))

    return {"ok": True}


async def run_bot():
    await dp.start_polling(bot)


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await asyncio.gather(run_api(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
