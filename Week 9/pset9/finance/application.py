import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT stock, price, SUM(shares) AS total_shares, (price * SUM(shares)) AS total FROM purchases WHERE user_id = ? GROUP BY stock", session["user_id"])

    total_list = []
    for i, stock in enumerate(stocks):
        total_list.append(stock["price"] * stock["total_shares"])
        stocks[i]["stock_name"] = lookup(stock["stock"])["name"]

    current_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    total_cash = sum(total_list) + current_cash[0]["cash"]

    return render_template("index.html", current_cash=current_cash[0]["cash"], total=total_cash, stocks=stocks)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form["symbol"]
        shares = request.form["shares"]
        
        if not symbol or not shares:
            return apology("fill the fields")
        elif not shares.isdigit() or int(shares) <= 0:
            return apology("type a positive\nint number")

        stock = lookup(symbol)

        if not stock:
            return apology("stock's not found")

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        total = int(shares) * stock["price"]

        if cash[0]["cash"] < total:
            return apology("you cant have\nmoney to buy")
        else:
            calc = cash[0]["cash"] - total

            db.execute("UPDATE users SET cash = ? WHERE id = ?", calc, session["user_id"])
            db.execute("INSERT INTO purchases (user_id, stock, price, shares) VALUES (?, ?, ?, ?)", session["user_id"], stock["symbol"], stock["price"], shares)

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    stocks = db.execute("SELECT stock, shares, price, purchase_date FROM purchases WHERE user_id = ?", session["user_id"])
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form["symbol"])
        if stock:
            return render_template("quoted.html", stock=stock)
        else:
            return apology("stock's not found")
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_confirm = request.form["confirmation"]

        check_username = db.execute("SELECT * FROM users WHERE username = ?", username)

        if not username or not password or not password_confirm:
            return apology("fill the fields")
        elif check_username:
            return apology("username already exists")
        elif password != password_confirm:
            return apology("password do not\nmatch")

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, generate_password_hash(password))

        return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change password"""
    if request.method == "POST":
        cur_pass = request.form["current-password"]
        new_pass = request.form["password"]
        confirm_pass = request.form["confirmation"]
        
        if not cur_pass or not new_pass or not confirm_pass:
            return apology("fill the fields")
        
        user_pass = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])

        if check_password_hash(user_pass[0]["hash"], cur_pass):
            if new_pass == confirm_pass:
                db.execute("UPDATE users SET hash = ? WHERE id = ?", generate_password_hash(new_pass), session["user_id"])
            else:
                return apology("password not match")
        else:
            return apology("wrong password")
            
        return redirect("/")
    else:
        return render_template("change-password.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form["symbol"]
        shares = request.form["shares"]

        stocks = db.execute("SELECT stock, price, SUM(shares) AS total_shares FROM purchases WHERE stock = ? GROUP BY stock", symbol)

        if not symbol or not shares:
            return apology("fill the fields")
        elif not shares.isdigit() or int(shares) <= 0:
            return apology("type a positive\nint number")
        elif not stocks:
            return apology("stock's not found")
        elif int(shares) > stocks[0]["total_shares"]:
            return apology("you don't have the\nexpected amount of shares")

        value = stocks[0]["price"] * int(shares)

        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", value, session["user_id"])

        if int(shares) == stocks[0]["total_shares"]:
            db.execute("DELETE FROM purchases WHERE stock = ? and user_id = ?", symbol, session["user_id"])
        elif int(shares) < stocks[0]["total_shares"]:
            db.execute("INSERT INTO purchases (user_id, stock, price, shares) VALUES (?, ?, ?, ?)", session["user_id"], symbol, stocks[0]["price"], -int(shares))

        return redirect("/")
    else:
        stocks = db.execute("SELECT stock FROM purchases WHERE user_id = ? GROUP BY stock", session["user_id"])
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
