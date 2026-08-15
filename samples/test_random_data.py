from lounger.log import log
from lounger.testdata import *


def test_random_testdata():
    # 随机一个名字
    log.info(f"名字：" + first_name())
    log.info("名字(男)：" + first_name(gender="male"))
    log.info("名字(女)：" + first_name(gender="female"))
    log.info("名字(中文男)：" + first_name(gender="male", language="zh"))
    log.info("名字(中文女)：" + first_name(gender="female", language="zh"))

    # 随机一个姓
    log.info("姓:" + last_name())
    log.info("姓(中文):" + last_name(language="zh"))

    # 随机一个姓名
    log.info("姓名:" + username())
    log.info("姓名(中文):" + username(language="zh"))

    # 随机一个生日
    log.info(f"生日: {get_birthday()}")
    log.info(f"生日字符串: {get_birthday(as_str=True)}")
    log.info(f"生日年龄范围: {get_birthday(start_age=20, stop_age=30)}")

    # 日期
    log.info(f"日期(当前): {get_date()}")
    log.info(f"日期(昨天): {get_date(-1)}")
    log.info(f"日期(明天): {get_date(1)}")

    log.info(f"当月：{get_month()}")
    log.info(f"上个月：{get_month(-1)}")
    log.info(f"下个月：{get_month(1)}")

    log.info(f"今年：{get_year()}")
    log.info(f"去年：{get_year(-1)}")
    log.info(f"明年：{get_year(1)}")

    # 数字
    log.info(f"数字(8位): {get_digits(8)}")

    # 邮箱
    log.info("邮箱:" + get_email())

    # 浮点数
    log.info(f"浮点数: {get_float()}")
    log.info(f"浮点数范围: {get_float(min_size=1.0, max_size=2.0)}")

    # 随机时间
    log.info(f"当前时间: {get_now_datetime()}")
    log.info("当前时间(格式化字符串):" + get_now_datetime(strftime=True))
    log.info(f"未来时间: {get_future_datetime()}")
    log.info("未来时间(格式化字符串):" + get_future_datetime(strftime=True))
    log.info(f"过去时间: {get_past_datetime()}")
    log.info("过去时间(格式化字符串):" + get_past_datetime(strftime=True))

    # 随机数据
    log.info(f"整型: {get_int()}")
    log.info(f"整型32位: {get_int32()}")
    log.info(f"整型64位: {get_int64()}")
    log.info("MD5:" + get_md5())
    log.info("UUID:" + get_uuid())

    log.info("单词:" + get_word())
    log.info("单词组(3个):" + get_words(3))

    log.info("手机号:" + get_phone())
    log.info("手机号(移动):" + get_phone(operator="mobile"))
    log.info("手机号(联通):" + get_phone(operator="unicom"))
    log.info("手机号(电信):" + get_phone(operator="telecom"))

    # 在线时间
    log.info("当前时间戳:" + online_timestamp())
    log.info("当前日期时间:" + online_now_datetime())
