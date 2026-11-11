import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from . import config, db, emoji, panel, runner
from .handlers import pro_reminder, restore_giveaways, router, season_payouts


GROUP_COMMANDS = [  # guruhdagi buyruqlar menyusi; is_ephemeral - buyruq va javobni faqat yozgan odam ko'radi
    BotCommand(command="game", description="🎮 Yangi o'yin"),
    BotCommand(command="extend", description="⏳ Ro'yxatni uzaytirish (daqiqa): /extend yoki /extend 5"),
    BotCommand(command="start", description="▶️ Darhol boshlash (admin)"),
    BotCommand(command="couplegame", description="💞 Paralar o'yini"),
    BotCommand(command="groupgame", description="⚪⚫ Oq-Qora o'yini (ikki jamoa)"),
    BotCommand(command="couplestart", description="❤️ Paralar o'yinini boshlash"),
    BotCommand(command="couplestop", description="💔 Paralar o'yinini to'xtatish (admin)"),
    BotCommand(command="stop", description="🛑 O'yinni to'xtatish (admin)"),
    BotCommand(command="leave", description="🚪 O'yindan chiqish (Pro)"),
    BotCommand(command="next", description="🔔 Keyingi o'yinda xabar berish", is_ephemeral=True),
    BotCommand(command="players", description="👥 Tiriklar va o'liklar", is_ephemeral=True),
    BotCommand(command="send", description="💸 Pul: /send 100 10 yoki reply + /send 100"),
    BotCommand(command="give", description="💎 Olmos: /give 10 2 yoki reply + /give 5"),
    BotCommand(command="mycouple", description="💞 Mening param"),
    BotCommand(command="settings", description="⚙️ Sozlamalar (admin)"),
    BotCommand(command="top", description="🏆 Guruh reytingi", is_ephemeral=True),
    BotCommand(command="rules", description="📜 Rollar", is_ephemeral=True),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env o'zgaruvchisi kerak")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await db.init()
    bot.session.middleware(runner.BackToGroup())
    bot.session.middleware(emoji.PremiumEmoji())
    emoji.load_roles(config.ROLE_EMOJI, config.ICON_EMOJI)  # rol portretlari va belgilar (premium)
    await emoji.load_pack(bot, config.EMOJI_PACK)  # bo'sh: o'chiq (to'ldirilsa rollarni almashtiradi)
    runner.BOT_USERNAME = (await bot.me()).username
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands([
        BotCommand(command="profile", description="👤 Profil"),
        BotCommand(command="role", description="🎭 Mening rolim"),
        BotCommand(command="shop", description="🛒 Do'kon"),
        BotCommand(command="pro", description="🌟 Pro akkaunt"),
        BotCommand(command="nickname", description="🏷 Nickname (Pro 3)"),
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
    runner.spawn(season_payouts(bot))
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
