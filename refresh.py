#!/usr/bin/env python3
"""Pull the Pawkit CS360 data from Zoho CRM through the API and write raw/crm.json.

Needs ~/.config/pawkit-cs360/zoho.json from zoho_setup.py (read-only self client).
Same data shape as the first browser snapshot, so build.py works unchanged.
WhatsApp counts for older days are cached in raw/wa_cache.json; today and yesterday
are re-counted every run, older days once an hour, to keep API use low.
"""
import calendar, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.expanduser("~/.config/pawkit-cs360/zoho.json")
SGT = timezone(timedelta(hours=8))
W = "woztellplatformintegration__"


def post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


class Zoho:
    def __init__(self):
        self.c = json.load(open(CFG))
        self.api = self.c.get("api_domain", "https://www.zohoapis.com")
        self.tok, self.exp = None, 0

    def token(self):
        if not self.tok or time.time() > self.exp - 60:
            j = post(self.c.get("accounts", "https://accounts.zoho.com") + "/oauth/v2/token", {
                "grant_type": "refresh_token", "refresh_token": self.c["refresh_token"],
                "client_id": self.c["client_id"], "client_secret": self.c["client_secret"]})
            if "access_token" not in j:
                raise SystemExit("Zoho token refresh failed: %s" % j.get("error", j))
            self.tok, self.exp = j["access_token"], time.time() + int(j.get("expires_in", 3600))
        return self.tok

    def req(self, path, body=None):
        h = {"Authorization": "Zoho-oauthtoken " + self.token()}
        data = None
        if body is not None:
            data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.api + path, data=data, headers=h, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return {}
            raise SystemExit("Zoho %s failed: %s %s" % (path, e.code, e.read()[:300]))

    def coql(self, q):
        return self.req("/crm/v5/coql", {"select_query": q})

    def all(self, q):
        out, off = [], 0
        while True:
            j = self.coql("%s limit %d, 2000" % (q, off))
            out += j.get("data", [])
            if not j.get("info", {}).get("more_records"):
                return out
            off += 2000


def customer_history(z, today):
    """Per-customer history from every booking: first completed visit (for 'repeat'), and who is due
    for grooming or a vaccination. Heavy (all bookings), so it is cached and rebuilt once an hour."""
    path = os.path.join(HERE, "raw", "hist_cache.json")
    try:
        with open(path) as f:
            c = json.load(f)
        if time.time() - c.get("_t", 0) < 3600 and c.get("day") == today.isoformat():
            return c
    except (OSError, ValueError):
        c = None
    try:
        rows = z.all("select Pet_Owner, Date_Time, Booking_Status, Service_Category, Next_grooming_appointment, "
                     "Next_vaccination_appointment, Customer_Clean_Name, Pet_Name, Area, Partner_Name.Name from Booking where Date_Time is not null")
    except SystemExit:
        if c:
            return c  # keep the last good copy if this big query fails
        raise
    t = today.isoformat()
    by = {}
    for r in rows:
        o = r.get("Pet_Owner")
        if isinstance(o, dict) and o.get("id"):
            by.setdefault(o["id"], []).append(r)
    first, repeat_owners = {}, 0
    groom, vacc = [], []
    first_name = lambda n: (n or "").strip().split(" ")[0][:20]
    for oid, rs in by.items():
        done = sorted((r for r in rs if r.get("Booking_Status") == "Completed"), key=lambda r: r["Date_Time"])
        if not done:
            continue
        first[oid] = done[0]["Date_Time"][:10]
        if len(done) >= 2:
            repeat_owners += 1
        future = [r for r in rs if r["Date_Time"][:10] > t and r.get("Booking_Status") not in ("Cancelled", "Not fulfilled", "Refund", "No show")]
        for cat, out, lo, hi, nxt in (("Grooming", groom, 35, 180, "Next_grooming_appointment"), ("Vaccination", vacc, 335, 450, "Next_vaccination_appointment")):
            d = [r for r in done if r.get("Service_Category") == cat]
            if not d or any(r.get("Service_Category") == cat for r in future):
                continue
            last = d[-1]
            days = (today - datetime.fromisoformat(last["Date_Time"][:10]).date()).days
            sugg = (last.get(nxt) or "")[:10] or None
            due_by_date = bool(sugg and sugg <= (today + timedelta(days=30)).isoformat())
            if not (lo <= days <= hi or (due_by_date and days >= 14 and days <= 450)):
                continue
            out.append({"n": first_name(last.get("Customer_Clean_Name")), "pet": (last.get("Pet_Name") or "")[:40], "last": last["Date_Time"][:10],
                        "days": days, "cnt": len(d), "all": len(done), "area": last.get("Area"), "prov": last.get("Partner_Name.Name"),
                        "next": sugg, "bid": last.get("id")})
    groom.sort(key=lambda x: (-x["cnt"], x["days"]))
    vacc.sort(key=lambda x: x["days"], reverse=True)
    c = {"_t": time.time(), "day": t, "first": first,
         "cust": {"asof": datetime.now(SGT).isoformat(timespec="minutes"), "owners": len(first), "repeat_owners": repeat_owners,
                  "groom": groom[:400], "vacc": vacc[:200], "groom_total": len(groom), "vacc_total": len(vacc)}}
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, path)
    return c


def rng(d):
    return "between '%sT00:00:00+08:00' and '%sT23:59:59+08:00'" % (d, d)


def main():
    z = Zoho()
    now = datetime.now(SGT)
    today = now.date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    start, end14 = days[0], days[-1]
    eom = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    next_sun = today + timedelta(days=13 - today.weekday())  # Sunday of next week (>= today+7)
    end_vis = max(eom, next_sun).isoformat()

    users = {u["id"]: u["full_name"] for u in z.req("/crm/v5/users?type=AllUsers&per_page=200").get("users", [])}
    nm = lambda v: users.get(v["id"]) if isinstance(v, dict) and v.get("id") else None

    # WhatsApp per day (cached)
    cpath = os.path.join(HERE, "raw", "wa_cache.json")
    try:
        with open(cpath) as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}  # missing or damaged cache: just re-count all days
    wa = {}
    for d in days:
        c = cache.get(d)
        fresh = d >= (today - timedelta(days=1)).isoformat()
        if c and not fresh and time.time() - c.get("_t", 0) < 3600:
            wa[d] = {k: c[k] for k in ("in", "out", "chats")}; continue
        a = z.coql("select %sDirection, COUNT(id) from %sWoztell_logs where %sMessage_Date_time %s group by %sDirection" % (W, W, W, rng(d), W))
        o = {x[W + "Direction"]: x["COUNT(id)"] for x in a.get("data", [])}
        u = z.coql("select %sFrom, COUNT(id) from %sWoztell_logs where %sMessage_Date_time %s and %sDirection = 'In' group by %sFrom limit 2000" % (W, W, W, rng(d), W, W))
        wa[d] = {"in": o.get("In", 0), "out": o.get("Out", 0), "chats": len(u.get("data", []))}
        cache[d] = dict(wa[d], _t=time.time())
    cache = {k: v for k, v in cache.items() if k >= start}
    ctmp = cpath + ".%d.tmp" % os.getpid()
    with open(ctmp, "w") as f:
        json.dump(cache, f)
    os.replace(ctmp, cpath)

    hist = customer_history(z, today)
    first = hist["first"]
    F = "Created_Time, Date_Time, End_Time, Booking_Status, Service_Category, Created_By, Partner_Name.Name, Area, Invoice_Status, Payment_Method, Base_Price, Pet_Owner"

    def owner(r):
        o = r.get("Pet_Owner")
        return o.get("id") if isinstance(o, dict) else None

    def repeat(r):  # the customer had a completed visit before this booking's date
        f = first.get(owner(r) or "")
        when = (r.get("Date_Time") or r.get("Created_Time") or "")[:10]
        return bool(f and when and f < when)
    slim = lambda r: {"c": r.get("Created_Time"), "d": r.get("Date_Time"), "e": r.get("End_Time"), "s": r.get("Booking_Status"),
                      "cat": r.get("Service_Category"), "src": None, "by": nm(r.get("Created_By")), "p": r.get("Partner_Name.Name"),
                      "a": r.get("Area"), "inv": r.get("Invoice_Status"), "pay": r.get("Payment_Method"),
                      "amt": r.get("Base_Price"), "o": (owner(r) or "")[-7:] or None, "rep": repeat(r)}
    start31 = (today - timedelta(days=13)).replace(day=1).isoformat()  # month of the oldest pickable day
    created = [slim(r) for r in z.all("select %s from Booking where Created_Time between '%sT00:00:00+08:00' and '%sT23:59:59+08:00'" % (F, start31, end14))]
    visits = [slim(r) for r in z.all("select %s from Booking where Date_Time between '%sT00:00:00+08:00' and '%sT23:59:59+08:00'" % (F, start31, end_vis))]

    comp = [{"n": c.get("Name"), "cd": c.get("Complaint_Date"), "c": c.get("Created_Time"), "s": c.get("Complaint_Status"),
             "pr": c.get("Priority"), "cat": c.get("Complaint_Category"), "p": c.get("Provider.Name"), "f": c.get("Follow_up_Date"),
             "rf": c.get("Refund_Required"), "ra": c.get("Refund_Amount"),
             "desc": " ".join((c.get("Complaint_Description") or "").split())[:400], "res": " ".join((c.get("Resolution") or "").split())[:250]}
            for c in z.all("select Name, Complaint_Date, Created_Time, Complaint_Status, Priority, Complaint_Category, Provider.Name, Follow_up_Date, Refund_Required, Refund_Amount, Complaint_Description, Resolution from Complaints where id is not null")]

    tasks = [{"sub": t.get("Subject"), "s": t.get("Status"), "pr": t.get("Priority"), "due": t.get("Due_Date"), "own": nm(t.get("Owner")),
              "by": nm(t.get("Created_By")), "type": t.get("Task_Type"), "svc": t.get("Service_Type"), "ho": t.get("Handover_To"),
              "hos": t.get("Handover_Status"), "dl": t.get("Action_Deadline"), "c": t.get("Created_Time"), "cl": t.get("Closed_Time"),
              "bid": t.get("Booking_ID"), "wait": t.get("Waiting_On"), "prov": t.get("Provider_Assigned"), "inv": t.get("Invoiced"),
              "paid": t.get("Paid"), "gcal": t.get("GCal_Updated"), "form": t.get("Form_Signed"), "comp": t.get("Compensation_Requested"),
              "conf": t.get("Confirmed_Date_Time")}
             for t in z.all("select Subject, Status, Priority, Due_Date, Owner, Created_By, Task_Type, Service_Type, Handover_To, Handover_Status, Action_Deadline, Created_Time, Closed_Time, Booking_ID, Waiting_On, Provider_Assigned, Invoiced, Paid, GCal_Updated, Form_Signed, Compensation_Requested, Confirmed_Date_Time from Tasks where id is not null")]

    orders = [{"n": o.get("Name"), "d": o.get("Order_Date"), "type": o.get("Order_Type"), "s": o.get("Order_Status"), "pay": o.get("Payment_Status"),
               "ful": o.get("Fulfilment_Status"), "by": o.get("Processed_By"), "agent": nm(o.get("Assign_Agent")), "dm": o.get("Delivery_Method"),
               "urg": o.get("Urgency_level"), "tot": o.get("Total_Order_Amount"), "out": o.get("Outstanding_Amount"), "paid": o.get("Amount_Paid"),
               "disp": o.get("Dispatch_Date"), "exp": o.get("Expected_Delivery_Date"), "del": o.get("Delivered_Date"),
               "xi": o.get("Xero_Invoice_Number"), "c": o.get("Created_Time")}
              for o in z.all("select Name, Order_Date, Order_Type, Order_Status, Payment_Status, Fulfilment_Status, Processed_By, Assign_Agent, Delivery_Method, Urgency_level, Total_Order_Amount, Outstanding_Amount, Amount_Paid, Dispatch_Date, Expected_Delivery_Date, Delivered_Date, Xero_Invoice_Number, Created_Time from Order_Processing where id is not null")]

    items = [{"n": i.get("Name"), "code": i.get("Item_Code"), "q": i.get("Qty_On_Hand"), "r": i.get("Reserved_Qty"),
              "up": i.get("Unit_Price"), "cp": i.get("Cost_Price"), "sync": i.get("Last_Synced")}
             for i in z.all("select Name, Item_Code, Qty_On_Hand, Reserved_Qty, Unit_Price, Cost_Price, Last_Synced from Xero_Items where id is not null")]

    s30 = (today - timedelta(days=30)).isoformat()
    inv = [{"d": b.get("Date_Time"), "s": b.get("Booking_Status"), "inv": b.get("Invoice_Status"), "po": b.get("Paid_On"),
            "pm": b.get("Payment_Method"), "amt": b.get("Base_Price"), "cat": b.get("Service_Category")}
           for b in z.all("select Date_Time, Booking_Status, Invoice_Status, Paid_On, Payment_Method, Base_Price, Service_Category from Booking where Date_Time between '%sT00:00:00+08:00' and '%sT23:59:59+08:00'" % (s30, end14))]

    out = {"generated": now.isoformat(timespec="minutes"), "visits_until": end_vis, "wa": wa, "created": created, "visits": visits, "comp": comp, "cust": hist["cust"],
           "tasks": tasks, "orders": orders, "items": items, "inv": inv}
    tmp = os.path.join(HERE, "raw", "crm.json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, os.path.join(HERE, "raw", "crm.json"))
    print(now.strftime("%Y-%m-%d %H:%M"), "ok", len(created), "made,", len(visits), "visits,", len(tasks), "tasks,", len(comp), "complaints")


if __name__ == "__main__":
    main()
