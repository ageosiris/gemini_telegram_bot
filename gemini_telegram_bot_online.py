# -*- coding: utf-8 -*-

import os
import io
import asyncio
from datetime import datetime
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКА ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OWNER_ID = os.environ.get("OWNER_ID")

# --- ИНИЦИАЛИЗАЦИЯ GEMINI ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Убедитесь, что используете правильную модель. Для генерации изображений может быть нужна другая.
    # На сентябрь 2025 года для генерации из текста и картинки используется 'gemini-1.5-flash' или 'gemini-1.5-pro'
    model = genai.GenerativeModel('gemini-1.5-flash') 
    print("Модель Gemini успешно инициализирована.")
except Exception as e:
    print(f"Ошибка при инициализации Gemini: {e}")
    model = None

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ОБРАБОТКИ ИЗОБРАЖЕНИЙ ---

async def process_image_with_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_file_id: str, user_prompt: str):
    """
    Основная логика обработки изображения: скачивание, отправка в Gemini, ответ пользователю и отправка логов владельцу.
    """
    status_message = await update.message.reply_text("✅ Получил задачу. Начинаю обработку...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='upload_photo')
    
    try:
        print(f"Получен запрос на редактирование. Промпт: '{user_prompt}'")
        photo_file = await context.bot.get_file(photo_file_id)
        file_bytes = await photo_file.download_as_bytearray()
        
        # --- НОВИНКА: Отправка исходного изображения владельцу ---
        try:
            user = update.effective_user
            caption = f"Пользователь {user.first_name} (@{user.username}, ID: {user.id}) прислал фото с запросом:\n\n'{user_prompt}'"
            await context.bot.send_photo(chat_id=OWNER_ID, photo=bytes(file_bytes), caption=caption)
            print(f"Исходное фото отправлено владельцу (ID: {OWNER_ID})")
        except Exception as e:
            print(f"Не удалось отправить исходное фото владельцу: {e}")
        # --- КОНЕЦ НОВОВВЕДЕНИЯ ---

        img = Image.open(io.BytesIO(file_bytes))

        await status_message.edit_text("⏳ Отправляю данные в нейросеть Gemini... Это может занять до минуты.")
        
        # Примечание: Для редактирования/создания изображений промпт должен быть более конкретным.
        # Например: "сделай фон синим", "добавь на фото кота в очках"
        full_prompt = [user_prompt, img]
        
        response = await asyncio.to_thread(model.generate_content, full_prompt)

        await status_message.edit_text("🎨 Нейросеть закончила работу. Анализирую ответ...")

        # Проверка, есть ли в ответе сгенерированное изображение
        if response.parts and response.parts[0].inline_data:
            image_part = response.parts[0]
            
            await status_message.edit_text("✅ Изображение получено! Готовлю его к отправке...")
            generated_image_data = image_part.inline_data.data
            
            # --- НОВИНКА: Отправка сгенерированного изображения владельцу ---
            try:
                await context.bot.send_photo(chat_id=OWNER_ID, photo=generated_image_data, caption="✅ Результат генерации для пользователя.")
                print(f"Сгенерированное фото отправлено владельцу (ID: {OWNER_ID})")
            except Exception as e:
                print(f"Не удалось отправить сгенерированное фото владельцу: {e}")
            # --- КОНЕЦ НОВОВВЕДЕНИЯ ---
            
            # Отправка результата пользователю
            await update.message.reply_photo(photo=generated_image_data, caption=f"Готово! ✨\nВаш запрос: '{user_prompt}'")
            await status_message.delete()
            print("Отредактированное изображение успешно отправлено пользователю.")
        else:
            text_explanation = response.text if hasattr(response, 'text') and response.text else "Модель не предоставила объяснения."
            print(f"Изображение не было сгенерировано. Ответ от API: '{text_explanation}'")
            error_text = (f"😥 Модель не смогла сгенерировать изображение.\n\n"
                          f"**Ответ от нейросети:**\n_{text_explanation}_\n\n"
                          "Попробуйте переформулировать запрос, сделав его проще.")
            await status_message.edit_text(error_text, parse_mode='Markdown')

    except google_exceptions.BadRequest as e:
        print(f"Ошибка BadRequest от Google API: {e}")
        error_text = ("😥 **Произошла ошибка (400 Bad Request).**\n\n"
                      "Чаще всего это означает, что **ваше местоположение не поддерживается** для использования API.\n\n"
                      "➡️ **Решение:** Попробуйте использовать VPN-сервис с подключением к серверу в США или другой поддерживаемой стране.")
        await status_message.edit_text(error_text, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Неизвестная ошибка при обработке изображения: {e}")
        error_text = ("😥 Ой, не удалось обработать ваше изображение. \n\n"
                      "Возможные причины:\n"
                      "- Запрос нарушает политику безопасности.\n"
                      "- Произошла внутренняя ошибка модели.\n\n"
                      "Попробуйте переформулировать запрос или использовать другое фото.")
        await status_message.edit_text(error_text)

# --- ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ (остаются без изменений) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я твой помощник на базе нейросети Gemini от Google. "
        "Я умею отвечать на вопросы и **редактировать фотографии**.\n\n"
        "➡️ **Для текста:** Просто задай мне любой вопрос.\n"
        "🖼️ **Для фото:** Отправь мне изображение, а я спрошу, что с ним сделать."
    )
    await update.message.reply_html(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🤖 **Как мной пользоваться:**\n\n"
        "1.  **Ответы на вопросы:**\n"
        "    Просто напиши мне свой вопрос текстом.\n\n"
        "2.  **Редактирование фото:**\n"
        "    - **Способ 1:** Отправь фото с подписью, что нужно сделать.\n"
        "    - **Способ 2:** Сначала отправь фото. Я его получу и попрошу тебя написать, что с ним сделать, в следующем сообщении."
    )
    await update.message.reply_html(help_text)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'pending_photo_id' in context.user_data:
        photo_id = context.user_data.pop('pending_photo_id')
        user_prompt = update.message.text
        await process_image_with_prompt(update, context, photo_id, user_prompt)
        return

    if not model:
        await update.message.reply_text("Извините, модель Gemini не инициализирована.")
        return

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        print(f"Получен текстовый запрос: {user_text}")
        response = await asyncio.to_thread(model.generate_content, user_text)
        await update.message.reply_text(response.text)
        print("Текстовый ответ от Gemini успешно отправлен.")
    except Exception as e:
        print(f"Ошибка при обработке текста: {e}")
        await update.message.reply_text("😥 Ой, не удалось обработать ваш текстовый запрос. Попробуйте позже.")

async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not model:
        await update.message.reply_text("Извините, модель Gemini не инициализирована.")
        return
        
    user_prompt = update.message.caption
    photo_file = update.message.photo[-1]

    if user_prompt:
        await process_image_with_prompt(update, context, photo_file.file_id, user_prompt)
    else:
        context.user_data['pending_photo_id'] = photo_file.file_id
        
        if len(update.message.photo) > 1:
            await update.message.reply_text("Вы отправили несколько фото. Я буду работать с последним.\n\nТеперь, пожалуйста, напишите в следующем сообщении, что с ним нужно сделать.", quote=True)
        else:
            await update.message.reply_text("Отличное фото! Теперь, пожалуйста, напишите в следующем сообщении, что с ним нужно сделать.", quote=True)

def main() -> None:
    """Основная функция для запуска бота."""
    print("Запуск бота...")
    
    # --- УДАЛЕНО: Создание папок больше не требуется ---
    # if not os.path.exists('user_images'):
    #     os.makedirs('user_images')
    # if not os.path.exists('generated_images'):
    #     os.makedirs('generated_images')

    if TELEGRAM_TOKEN == "ВАШ_ТЕЛЕГРАМ_ТОКЕН_СЮДА" or GEMINI_API_KEY == "ВАШ_GEMINI_API_КЛЮЧ_СЮДА" or OWNER_ID == 123456789:
        print("\n!!! ВНИМАНИЕ !!!\nПожалуйста, укажите ваши TELEGRAM_TOKEN, GEMINI_API_KEY и OWNER_ID в коде файла.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image_message))

    print("Бот запущен и готов к работе. Нажмите Ctrl+C для остановки.")
    application.run_polling()

if __name__ == "__main__":
    main()