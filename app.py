from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
app.secret_key = "kare_store_secret"

# ---------------- GOOGLE SHEETS SETUP ----------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json", scope
)
client = gspread.authorize(creds)

sheet = client.open("KARE_Store_Inventory")
users_sheet = sheet.worksheet("Users")
inward_sheet = sheet.worksheet("Inward")
outward_sheet = sheet.worksheet("Outward")
stock_sheet = sheet.worksheet("Stock")

# ---------------- AUTH HELPERS ----------------
def login_required():
    return 'user' in session

def admin_only():
    return session.get('role') == 'Admin'

# ---------------- FIFO LOGIC ----------------
def fifo_issue(item, qty):
    records = inward_sheet.get_all_records()
    remaining = qty
    total_cost = 0

    for i, r in enumerate(records):
        # Skip rows with missing data
        if not r.get('Item') or not r.get('Balance') or not r.get('Unit Cost'):
            continue

        sheet_item = str(r['Item']).strip().lower()

        try:
            balance = int(float(r['Balance']))
            unit_cost = float(r['Unit Cost'])
        except:
            continue  # Skip invalid rows safely

        if sheet_item == item.strip().lower() and balance > 0:
            used = min(balance, remaining)
            total_cost += used * unit_cost
            remaining -= used

            # Update Balance column (F = 6)
            inward_sheet.update_cell(i + 2, 6, balance - used)

            if remaining == 0:
                break

    if remaining > 0:
        raise Exception("Insufficient stock or invalid inward data")

    return total_cost



def update_stock(item, change):
    records = stock_sheet.get_all_records()
    items = [r['Item'] for r in records]

    if item in items:
        row = items.index(item) + 2
        current = int(stock_sheet.cell(row, 2).value)
        stock_sheet.update_cell(row, 2, current + change)
    else:
        stock_sheet.append_row([item, change])

# ---------------- ROUTES ----------------
@app.route('/', methods=['GET'])
def index():
    if not login_required():
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']

        users = users_sheet.get_all_records()
        print(users)  # DEBUG

        for u in users:
            if u['Username'].strip().lower() == uname.strip().lower() and \
               u['Password'].strip() == pwd.strip():
                session['user'] = uname
                session['role'] = u['Role']
                return redirect(url_for('index'))

        return "Invalid credentials"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/inward', methods=['GET', 'POST'])
def inward():
    if not login_required():
        return redirect(url_for('login'))

    if request.method == 'POST':
        date = datetime.now().strftime("%d-%m-%Y")
        inward_sheet.append_row([
            date,
            request.form['item'],
            int(request.form['quantity']),
            float(request.form['cost']),
            request.form['supplier'],
            int(request.form['quantity'])
        ])
        update_stock(request.form['item'], int(request.form['quantity']))
        return redirect(url_for('inward'))

    return render_template('inward.html', records=inward_sheet.get_all_records())

@app.route('/outward', methods=['GET', 'POST'])
def outward():
    if not login_required():
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            item = request.form['item']
            qty = int(request.form['quantity'])
            issued_to = request.form['issued_to']

            cost = fifo_issue(item, qty)

            outward_sheet.append_row([
                datetime.now().strftime("%d-%m-%Y"),
                item,
                qty,
                issued_to,
                cost
            ])

            update_stock(item, -qty)
            return redirect(url_for('outward'))

        except Exception as e:
            return f"Outward Error: {str(e)}"

    return render_template(
        'outward.html',
        records=outward_sheet.get_all_records()
    )

@app.route('/stock')
def stock():
    if not login_required():
        return redirect(url_for('login'))
    return render_template('stock.html', stock=stock_sheet.get_all_records())

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)
