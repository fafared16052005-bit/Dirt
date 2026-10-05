import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiosqlite

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [7651390120]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AddProduct(StatesGroup):
    name = State()
    description = State()
    price = State()

class EditProduct(StatesGroup):
    choose_field = State()
    new_value = State()

async def init_db():
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL
            )
        """)
        await db.commit()

async def get_all_products():
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT id, name, description, price FROM products ORDER BY id") as cursor:
            return await cursor.fetchall()

async def get_product(product_id: int):
    async with aiosqlite.connect("shop.db") as db:
        async with db.execute("SELECT id, name, description, price FROM products WHERE id = ?", (product_id,)) as cursor:
            return await cursor.fetchone()

async def add_product(name: str, description: str, price: float):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            (name, description, price)
        )
        await db.commit()

async def update_product_field(product_id: int, field: str, value: str | float):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
        await db.commit()

async def delete_product(product_id: int):
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="✏️ Редактировать товар", callback_data="admin_edit")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="admin_list")],
    ])

def products_keyboard(products, prefix="view"):
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"{p[1]} — {p[3]} ₽",
            callback_data=f"{prefix}_{p[0]}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("👋 Добро пожаловать в наш магазин!\n\nИспользуй /catalog чтобы посмотреть товары.")

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message):
    products = await get_all_products()
    if not products:
        await message.answer("Каталог пока пуст 😔")
        return
    await message.answer("📦 Наши товары:", reply_markup=products_keyboard(products, prefix="view"))

@dp.callback_query(F.data.startswith("view_"))
async def view_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    text = f"<b>{product[1]}</b>\n\n{product[2] or 'Без описания'}\n\n💰 Цена: <b>{product[3]} ₽</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Оформить заказ", callback_data=f"order_{product_id}")],
        [InlineKeyboardButton(text="« Назад в каталог", callback_data="back_catalog")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back_catalog")
async def back_to_catalog(callback: CallbackQuery):
    products = await get_all_products()
    await callback.message.edit_text("📦 Наши товары:", reply_markup=products_keyboard(products, prefix="view"))
    await callback.answer()

@dp.callback_query(F.data.startswith("order_"))
async def order_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await callback.message.answer(f"✅ Заказ на товар <b>{product[1]}</b> принят!\nАдминистратор скоро свяжется с вами.", parse_mode="HTML")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🛒 Новый заказ!\nТовар: {product[1]}\nОт: @{callback.from_user.username or callback.from_user.id}\nID: {callback.from_user.id}")
        except:
            pass
    await callback.answer()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_keyboard())

@dp.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AddProduct.name)
    await callback.message.answer("Введите <b>название</b> товара:", parse_mode="HTML")
    await callback.answer()

@dp.message(AddProduct.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.description)
    await message.answer("Теперь введите <b>описание</b> товара:", parse_mode="HTML")

@dp.message(AddProduct.description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("Теперь введите <b>цену</b> (только число):", parse_mode="HTML")

@dp.message(AddProduct.price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Цена должна быть числом. Попробуйте ещё раз:")
        return
    data = await state.get_data()
    await add_product(data["name"], data["description"], price)
    await state.clear()
    await message.answer(f"✅ Товар <b>{data['name']}</b> успешно добавлен!", parse_mode="HTML")

@dp.callback_query(F.data == "admin_list")
async def admin_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    products = await get_all_products()
    if not products:
        await callback.message.answer("Товаров пока нет")
        await callback.answer()
        return
    text = "📋 Список товаров:\n\n"
    for p in products:
        text += f"<b>#{p[0]}</b> {p[1]} — {p[3]} ₽\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_edit")
async def admin_edit_start(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    products = await get_all_products()
    if not products:
        await callback.message.answer("Нет товаров для редактирования")
        await callback.answer()
        return
    await callback.message.answer("Выберите товар для редактирования:", reply_markup=products_keyboard(products, prefix="edit"))
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_"))
async def edit_choose_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await state.update_data(product_id=product_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data="field_name")],
        [InlineKeyboardButton(text="📝 Описание", callback_data="field_description")],
        [InlineKeyboardButton(text="💰 Цену", callback_data="field_price")],
    ])
    await callback.message.answer(f"Редактируем: <b>{product[1]}</b>\nЧто хотите изменить?", reply_markup=kb, parse_mode="HTML")
    await state.set_state(EditProduct.choose_field)
    await callback.answer()

@dp.callback_query(EditProduct.choose_field, F.data.startswith("field_"))
async def edit_choose_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    await state.update_data(field=field)
    await state.set_state(EditProduct.new_value)
    field_names = {"name": "новое название", "description": "новое описание", "price": "новую цену"}
    await callback.message.answer(f"Введите {field_names[field]}:")
    await callback.answer()

@dp.message(EditProduct.new_value)
async def edit_save_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data["field"]
    product_id = data["product_id"]
    value = message.text
    if field == "price":
        try:
            value = float(value.replace(",", "."))
        except ValueError:
            await message.answer("Цена должна быть числом. Попробуйте ещё раз:")
            return
    await update_product_field(product_id, field, value)
    await state.clear()
    await message.answer("✅ Изменения сохранены!")

@dp.callback_query(F.data == "admin_delete")
async def admin_delete_start(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    products = await get_all_products()
    if not products:
        await callback.message.answer("Нет товаров для удаления")
        await callback.answer()
        return
    await callback.message.answer("Выберите товар для удаления:", reply_markup=products_keyboard(products, prefix="delete"))
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_"))
async def delete_product_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if product:
        await delete_product(product_id)
        await callback.message.answer(f"🗑 Товар <b>{product[1]}</b> удалён", parse_mode="HTML")
    await callback.answer()

async def main():
    await init_db()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
