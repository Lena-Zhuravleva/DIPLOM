import datetime
from models import Supplier, Delivery


UNLOAD_PLACES = [
    {"id": "RAW_1", "title": "RAW-1 (рампа 1)"},
    {"id": "RAW_2", "title": "RAW-2 (рампа 1)"},
    {"id": "RAW_3", "title": "RAW-3 (рампа 2)"},
    {"id": "CRANE", "title": "КРАН (ЖД рампа)"},
]


def generate_slots(start_hour=8, end_hour=18, step_minutes=15):
    slots = []
    cur = datetime.datetime(2000, 1, 1, start_hour, 0)
    end = datetime.datetime(2000, 1, 1, end_hour, 0)
    while cur < end:
        slots.append(cur.time())
        cur += datetime.timedelta(minutes=step_minutes)
    return slots


def time_to_minutes(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


def overlaps(start_min: int, dur_min: int, slot_min: int) -> bool:
    return start_min <= slot_min < (start_min + dur_min)


def supplier_candidates(material_status: str):
    if material_status == 'critical':
        zones = ['local', 'regional', 'international']
    elif material_status == 'warning':
        zones = ['local', 'regional']
    else:
        zones = ['local', 'regional', 'international']

    q = Supplier.query.filter(Supplier.delivery_zone.in_(zones))
    suppliers = q.all()

    zone_rank = {z: i for i, z in enumerate(zones)}
    suppliers.sort(key=lambda s: (zone_rank.get(s.delivery_zone, 999), -float(s.rating or 0)))
    return suppliers


def slot_busy(day, slot_time, place):
    deliveries = Delivery.query.filter_by(date=day, unload_place=place).all()

    slot_min = time_to_minutes(slot_time)

    for d in deliveries:
        start_min = time_to_minutes(d.time_slot)
        duration = d.duration_min or 60

        if overlaps(start_min, duration, slot_min):
            return True

    return False
