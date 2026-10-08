import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from . import config, db, emoji, panel, runner
from .handlers import pro_reminder, restore_giveaways, router


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env o'zgaruvchisi kerak")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await db.init()
    bot.session.middleware(emoji.PremiumEmoji())
    await emoji.load_pack(bot, config.EMOJI_PACK)
    runner.BOT_USERNAME = (await bot.me()).username
    await bot.set_my_commands([
        BotCommand(command="game", description="🎮 Yangi o'yin"),
        BotCommand(command="extend", description="⏳ Ro'yxatni uzaytirish: /extend yoki /extend 60"),
        BotCommand(command="begin", description="▶️ Darhol boshlash (admin)"),
        BotCommand(command="couplegame", description="💞 Paralar o'yini"),
        BotCommand(command="couplestart", description="❤️ Paralar o'yinini boshlash"),
        BotCommand(command="stop", description="🛑 O'yinni to'xtatish (admin)"),
        BotCommand(command="leave", description="🚪 O'yindan chiqish"),
        BotCommand(command="next", description="🔔 Keyingi o'yinda xabar berish"),
        BotCommand(command="players", description="👥 Tiriklar va o'liklar"),
        BotCommand(command="send", description="💸 Pul: /send 100 10 yoki reply + /send 100"),
        BotCommand(command="give", description="💎 Olmos: /give 10 2 yoki reply + /give 5"),
        BotCommand(command="couple", description="❤️ Para bo'lish: reply yoki /couple @username"),
        BotCommand(command="uncouple", description="💔 Paradan chiqish"),
        BotCommand(command="mycouple", description="💞 Mening param"),
        BotCommand(command="settings", description="⚙️ Sozlamalar (admin)"),
        BotCommand(command="top", description="🏆 Guruh reytingi"),
        BotCommand(command="rules", description="📜 Rollar"),
    ], scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands([
        BotCommand(command="profile", description="👤 Profil"),
        BotCommand(command="role", description="🎭 Mening rolim"),
        BotCommand(command="shop", description="🛒 Do'kon"),
        BotCommand(command="pro", description="🌟 PRO akkaunt"),
        BotCommand(command="nickname", description="🏷 Nickname (PRO)"),
        BotCommand(command="paysupport", description="💳 To'lov bo'yicha yordam"),
        BotCommand(command="top", description="🏆 Reyting"),
        BotCommand(command="rules", description="📜 Rollar"),
    ], scope=BotCommandScopeAllPrivateChats())
    dp = Dispatcher()
    dp.include_router(router)
    await panel.start(bot)
    await runner.restore(bot)
    await restore_giveaways(bot)
    runner.spawn(pro_reminder(bot))
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
