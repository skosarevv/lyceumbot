import random
import re
import datetime

from aiogram import Bot, Dispatcher, executor, types

from exceptions import ClasException, GroupException, DateException, ParsingProcessException
from database import UserTable, ScheduleTable
from constants import TOKEN, SPAM_RESTRICTION, CLASSES, PROFILES, LINK, alt_profiles, available_days, teachers
import texts
import keyboards

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

message_logger = open('logs/messages.log', 'a', encoding='utf8')
user_db = UserTable()
schedule_db = ScheduleTable()


# CALLBACK HANDLERS

@dp.callback_query_handler(text="classes")
async def classes(callback: types.CallbackQuery):
    text = 'Список классов:\n\n'
    for i in range(24):
        text += CLASSES[i] + '\n'
        if i == 11:
            text += '\n'
    await callback.answer(text=text, show_alert=True)


@dp.callback_query_handler(text=['10', '11'])
async def set_class_number(callback: types.CallbackQuery):
    tg_id = callback.from_user.id

    func = keyboards.select_10_profile() if callback.data == '10' else keyboards.select_11_profile()
    await bot.edit_message_text(texts.GET_CLASS, tg_id, callback.message.message_id, reply_markup=func)
    user_db.set_state(tg_id, 1)

    user_db.set_clas_number(tg_id, int(callback.data))
    await callback.answer()


@dp.callback_query_handler(text=CLASSES)
async def set_class_profile(callback: types.CallbackQuery):
    tg_id = callback.from_user.id

    await bot.edit_message_text(texts.GET_GROUP, tg_id, callback.message.message_id,
                                reply_markup=keyboards.select_group())
    user_db.set_state(tg_id, 2)

    user_db.set_clas_number(tg_id, int(callback.data[:2]))
    user_db.set_clas_profile(tg_id, callback.data[2:])
    await callback.answer()


@dp.callback_query_handler(text=['1', '2'])
async def set_group(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    await bot.edit_message_text(texts.SUCCESS, tg_id, callback.message.message_id)
    user_db.set_state(tg_id, 3)

    user_db.set_group(tg_id, int(callback.data))
    await callback.answer()
    await help(callback.message)

@dp.callback_query_handler(text=teachers)
async def select_teacher(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    if callback.data == 'ᅠ':
        await callback.answer()
        return

    await bot.edit_message_text(texts.TEACHER_WARNING, tg_id, callback.message.message_id, parse_mode='HTML')
    await bot.send_message(tg_id, f'Преподаватель: {callback.data}\n{texts.SELECT_TDATE}', reply_markup=keyboards.select_tday(), parse_mode='HTML')
    await callback.answer()


@dp.callback_query_handler(text=['teachers_prev', 'teachers_next'])
async def change_teacher_list(callback: types.CallbackQuery):
    tg_id = callback.from_user.id

    if callback.data == 'teachers_prev':
        await bot.edit_message_text(texts.SELECT_TEACHER, tg_id, callback.message.message_id, reply_markup=keyboards.select_teacher_part1())
    else:
        await bot.edit_message_text(texts.SELECT_TEACHER, tg_id, callback.message.message_id,reply_markup=keyboards.select_teacher_part2())
    await callback.answer()


@dp.callback_query_handler(text=list(map(lambda item: item + 't', available_days)))
async def get_teacher(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    if await is_on_update():
        await bot.send_message(tg_id, texts.TABLE_UPDATING_ERROR)
        await callback.answer()
        return



    date = callback.data[:-1]
    teacher = callback.message.text[callback.message.text.index(':') + 2: callback.message.text.index('\n')]
    schedule = schedule_db.get_teacher(date, teacher)

    await log(f'get teacher: {callback.data} - {teacher}')

    added_classes = []  # пары, которые уже добавлены в сообщение
    answer_text = f'{date} • {teacher}\n\n'

    for i in range(1, 6):
        classes = []
        for line in schedule:
            if line[2] == i:
                classes.append(line)
        if classes:
            for clas in classes:
                if f'{i}{clas[5]}{PROFILES[clas[6] - 1]}' not in added_classes:
                    answer_text += f'{i}. {clas[5]}{PROFILES[clas[6] - 1]} - {clas[3]}   [{clas[8] if clas[8] not in ["None", "", None] else " — "}]\n'
                    added_classes.append(f'{i}{clas[5]}{PROFILES[clas[6] - 1]}')
        else:
            answer_text += f'{i}.\n'



    await bot.send_message(tg_id, answer_text)
    await callback.answer()


@dp.callback_query_handler()
async def get_by_button(callback: types.CallbackQuery):
    if callback.data in ['ᅠ', 'None']:
        await callback.answer()
        return
    await log(f'get by button: {callback.data}')

    tg_id = callback.from_user.id
    if not await process_checks(tg_id, spam=True):
        await callback.answer(show_alert=False)
        return
    try:
        schedule = await get_schedule(callback.data, user_db.get_clas_number(tg_id), user_db.get_clas_profile(tg_id), user_db.get_group(tg_id))
        await callback.message.answer(schedule, parse_mode='HTML')
    except ParsingProcessException:
        await callback.message.answer(texts.TABLE_UPDATING_ERROR)
    await callback.answer(show_alert=False)


# COMMAND HANDLERS

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await log(message)

    tg_id = message.from_user.id

    if not user_db.user_exists(tg_id):
        user_db.save_user(tg_id, message.from_user.username, message.from_user.first_name, None, None, None)
        await message.answer(texts.START)
        await message.answer('Для начала у' + texts.GET_CLASS_NUMBER[1:],
                             reply_markup=keyboards.select_class_num())

    elif user_db.get_state(tg_id) in [0, 1, 2]:
        user_db.set_state(message.from_user.id, 0)
        await message.answer(texts.GET_CLASS_NUMBER, reply_markup=keyboards.select_class_num())

    else:
        await message.answer(f'{texts.START}\n\n{texts.MORE_INFO}')


@dp.message_handler(commands=['help'])
async def help(message: types.Message):
    await log(message)

    await message.answer(texts.HELP, parse_mode='HTML')


@dp.message_handler(commands=['get'])
async def get(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    if ' ' in message.text:
        await process_messages(message)
        return

    await message.answer('Введите дату или выберите из кнопок ниже:', reply_markup=keyboards.select_day())


@dp.message_handler(commands=['link'])
async def link(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    # я так и не решил, какой вариант лучше
    answer_text = random.choice(['Ссылка на актуальное расписание:', 'Актуальная ссылка на расписание:']) + '\n' + LINK
    await message.answer(answer_text, disable_web_page_preview=True)


@dp.message_handler(commands=['list'])
async def list(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    answer_text = 'Список доступных дней:\n\n'
    for i in range(0, len(available_days), 5):
        answer_text += f'{available_days[i]} {available_days[i + 1]} {available_days[i + 2]} {available_days[i + 3]} {available_days[i + 4]}\n'
    await message.answer(answer_text)


@dp.message_handler(commands=['setclass'])
async def set_class(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    await message.answer(texts.GET_CLASS_NUMBER, reply_markup=keyboards.select_class_num())


@dp.message_handler(commands=['setgroup'])
async def set_group(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    if user_db.get_state(message.from_user.id) in [0, 1]:
        await set_class()
        return

    await message.answer(texts.GET_GROUP, reply_markup=keyboards.select_group())


@dp.message_handler(commands=['t', 'teacher'])
async def teacher(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id, signup=False):
        return

    await message.answer(texts.SELECT_TEACHER, reply_markup=keyboards.select_teacher_part1())


@dp.message_handler(commands=['settings'])
async def settings(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    await message.answer(texts.WIP)


@dp.message_handler(commands=['bells'])
async def bells(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    with open('resources/bells.jpg', 'rb') as photo:
        await message.answer_photo(photo)


@dp.message_handler(commands=['about'])
async def about(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    await message.answer(texts.ABOUT, parse_mode='HTML', disable_web_page_preview=True)


@dp.message_handler(commands=['formats'])
async def formats(message: types.Message):
    await log(message)
    if not await process_checks(message.from_user.id):
        return

    await message.answer(texts.FORMATS, parse_mode='HTML')


@dp.message_handler(commands=['delete'])
async def delete(message: types.Message):
    """Deletes user from Database"""
    await log(message)

    user_db.delete_user(message.from_user.id)
    await message.answer(texts.DELETE, parse_mode='HTML')


# MESSAGES HANDLER

@dp.message_handler()
async def process_messages(message: types.Message):
    await log(message)

    tg_id = message.from_user.id
    message_text = message.text
    try:
        state = user_db.get_state(tg_id)
    except TypeError:
        await message.answer(texts.SWW_ERROR)
        return

    if state in [0, 1]:
        # class processing
        user_db.set_state(tg_id, 0)
        await message.answer(texts.SIGNUP_ERROR)
        await message.answer(texts.GET_CLASS_NUMBER, reply_markup=keyboards.select_class_num())

    elif state == 2:
        # group processing
        await message.answer(texts.SIGNUP_ERROR)
        await message.answer(texts.GET_GROUP, reply_markup=keyboards.select_group())

    elif state == 3:
        # date processing
        if not await process_checks(tg_id, signup=True, spam=False):
            return

        if not message_text.startswith('/get'):
            if not await process_checks(tg_id, signup=False, spam=True):
                return

        clas_number = user_db.get_clas_number(tg_id)
        clas_profile = user_db.get_clas_profile(tg_id)
        group = user_db.get_group(tg_id)

        if message_text.startswith('/get'):
            if '.' in message_text:
                date = message_text.split(' ')[1]
            else:
                date = message_text.split()[1] + '.' + message_text.split()[2]

        elif re.fullmatch(r'\d\d([. ])\d\d', message_text):
            date = '.'.join(message_text.split()) if ' ' in message_text else message_text

        elif re.fullmatch(r'\d\d\.\d\d .* .*', message_text):
            elements = message_text.split()
            date = elements[0]
            clas_number = elements[1][:2]
            clas_profile = elements[1][2:]
            group = int(elements[2])

        elif re.fullmatch(r'\d\d \d\d .* .*', message_text):
            elements = message_text.split()
            date = f'{elements[0]}.{elements[1]}'
            clas_number = elements[2][:2]
            clas_profile = elements[2][2:]
            group = int(elements[3])

        else:
            await message.answer(texts.INVALID_FORMAT_ERROR)
            await message.answer(texts.FORMATS, parse_mode='HTML')
            return

        if clas_profile in alt_profiles:
            clas_profile = alt_profiles[clas_profile]

        try:
            if date not in available_days:
                raise DateException()

            schedule = await get_schedule(date, clas_number, clas_profile, group)
            await message.answer(schedule, parse_mode='HTML')
        except DateException:
            await message.answer(texts.NO_SCHEDULE_ERROR)
        except ClasException:
            await message.answer(texts.INVALID_CLASS_ERROR, reply_markup=keyboards.list_classes())
        except GroupException:
            await message.answer(texts.INVALID_GROUP_ERROR)
        except ParsingProcessException:
            await message.answer(texts.TABLE_UPDATING_ERROR)
    else:
        await message.answer(texts.SWW_ERROR)


# UTIL FUNCTIONS

async def log(message):
    message_logger.write(str(message) + '\n')
    message_logger.flush()


async def get_schedule(date: str, clas_number: int, clas_profile: str, group: int) -> str:
    if clas_profile not in PROFILES:
        raise ClasException
    if group not in [1, 2]:
        raise GroupException

    schedule = schedule_db.get(date, clas_number, clas_profile, group)
    if len(schedule) != 5:
        raise ParsingProcessException

    result_text = f'{str(schedule[0][5]) + (PROFILES.index(schedule[0][6]) + 1)} • группа {group} • {date}\n\n'

    for i in range(5):
        if schedule[i][3] is not None:
            classroom = schedule[i][8]
            teacher = schedule[i][4]
            result_text += f'{schedule[i][2]}. {schedule[i][3]}{" (" + teacher + ")" if teacher else ""}   [{classroom if classroom != "None" else " — "}]\n'
        else:
            if schedule[i][2] != 5:
                result_text += f'{i + 1}. ✖ \n'

    return result_text


# если не прошли проверки - возвращает False
async def process_checks(id, signup=True, spam=False, user_exists=True):
    if user_exists and not user_db.user_exists(id):
            await bot.send_message(id, texts.SWW_ERROR)
            return
    if signup and spam:
        return await check_signup(id) and await check_spam(id)
    if signup:
        return await check_signup(id)
    if spam:
        return await check_spam(id)
    return True


async def check_signup(id):
    if not user_db.user_exists(id):
        return False
    if user_db.get_state(id) in [0, 1, 2]:
        user_db.set_state(id, 0)
        await bot.send_message(id, texts.SIGNUP_ERROR)
        await bot.send_message(id, texts.GET_CLASS_NUMBER, reply_markup=keyboards.select_class_num())
        return False
    return True


async def check_spam(id):
    now = datetime.datetime.now()
    last_message = datetime.datetime.strptime(user_db.get_lastmessage(id), '%Y-%m-%d %H:%M:%S.%f')

    if abs((last_message - now).total_seconds()) < SPAM_RESTRICTION:
        await bot.send_message(id, texts.SPAM_ERROR)
        return False

    user_db.set_lastmessage(id, now)
    return True

async def is_on_update():
    schedule = schedule_db.get(available_days[-1], 11, 'эк', 2)
    return len(schedule) != 5


#


def main():
    executor.start_polling(dp)


if __name__ == '__main__':
    main()
