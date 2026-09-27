from datetime import datetime
from models import RepairRequest

def generate_request_no():
    prefix = datetime.now().strftime("RP-%Y%m")
    last = RepairRequest.query.filter(
        RepairRequest.request_no.like(prefix + "-%")
    ).order_by(RepairRequest.id.desc()).first()
    number = 1
    if last:
        try:
            number = int(last.request_no.split("-")[-1]) + 1
        except ValueError:
            pass
    return f"{prefix}-{str(number).zfill(3)}"
