# telegram_bot.py
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from finsight_agent import agent, UserInfos
from telegram import Update
from pprint import pprint
import asyncio
import os

API_KEY_TELEGRAM = os.environ['TELEGRAM_API']   

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = str(update.message.chat_id) 
    user_message = update.message.text
    id_user = update.message.from_user.id

    if id_user == 6494505476:
        # Roda o invoke síncrono em thread separada para não bloquear
        response = await asyncio.to_thread(
            agent.invoke,
            {"messages": [HumanMessage(user_message)]},
            {"configurable": {"thread_id": session_id}},
            context=UserInfos(name='Patrick', age=23, city='Porto Alegre')
        )

        pprint(response["messages"])
        print('==' * 10)

        content = response["messages"][-1].content
        if content:
            await update.message.reply_text(content)
        else:
            await update.message.reply_text("✅ Feito!")
    else:
        await update.message.reply_text("❌ Acesso negado.")

def main():
    TOKEN = API_KEY_TELEGRAM 

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print('🤖 Bot iniciado. Aguardando mensagens...')
    app.run_polling()

if __name__ == "__main__":
    main()