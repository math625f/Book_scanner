import requests
import xmltodict
import json
import mysql.connector
from serial import Serial
import re

config = {}

with open('env.json') as f:
    config = json.loads(f.read())

try:
    s = Serial('COM3')
except:
    print("Wasn't able to connect to Serial Port Scanner")
    pass

# Goodreads stuff
goodreads_key = config['goodreads_key']
goodreads_url = "https://www.goodreads.com/search/index.xml"


def do_scan():
    print("Awaiting scan...")
    return s.read(15).decode("UTF-8")


# MySQL stuff
db = mysql.connector.connect(
    host=config['host'],
    user=config['user'],
    passwd=config['passwd'],
    database=config['database']
)

author_table = config['author_table']
books_table = config['books_table']
jnct_table = config['jnct_table']
lang_table = config['lang_table']
series_table = config['series_table']

# Main loop
should_exit = False


def unfix(s):
    buf = []

    for i in range(0, len(s)):
        if re.search("[a-zA-Z0-9\s]", s[i]):
            buf.append(s[i])
        else:
            buf.append("&#{};".format(ord(s[i])))
    return "".join(buf)


def add_lang():
    c = db.cursor()
    print("What language do you want to add?")
    lang = input()
    print("What is the country code for this language? (Used to get flags, should be two letters)")
    print("Please consult http://flag-icon-css.lip.is/ for help on finding the correct country code")
    cc = input()
    c.execute("INSERT INTO `{}` (`id`, `lang`, `country_code`) VALUES(NULL, '{}', {})".format(lang_table, lang, cc))
    c.execute("SELECT LAST_INSERT_ID()")
    l_id = c.fetchone()[0]
    db.commit()
    return l_id


def select_lang():
    c = db.cursor()
    c.execute("SELECT * FROM {} WHERE 1".format(lang_table))
    res = c.fetchall()
    print("Select a language from list, or add a new one")
    print("[0] - Add new language")
    choice = "-1"
    ids = ["0"]
    for l in res:
        ids.append(str(l[0]))
        print("[{}] - {}".format(l[0], l[1].capitalize()))
    while choice not in ids:
        choice = input()
    if choice == "0":
        choice = add_lang()
    print(choice)
    return choice


def add_book(book, isbn):
    lang = select_lang()
    title = book['best_book']['title']
    small_image_url = book['best_book']['small_image_url']
    try:
        image_url = small_image_url.split('._')[0] + "._SX500_." + small_image_url.split('_.')[1]
    except IndexError:
        image_url = small_image_url
    year = book['original_publication_year']["#text"] if "@nil" not in book['original_publication_year'] else -1
    month = book['original_publication_month']["#text"] if "@nil" not in book['original_publication_month'] else -1
    day = book['original_publication_day']["#text"] if "@nil" not in book['original_publication_day'] else -1
    rating = book['average_rating']['#text'] if '#text' in book['average_rating'] else book['average_rating']
    bid = book['best_book']['id']['#text']
    wid = book['id']['#text']
    author_name = unfix(book['best_book']['author']['name'])
    author_id = book['best_book']['author']['id']["#text"]
    c = db.cursor()
    b_title = "(".join(title.split("(")[:-1])
    b_title = b_title if len(b_title) > 0 else title
    s_id = -1
    if re.search('(\(.*,?\s#?[0-9]*\))', title):
        s_title = " ".join(title.split("(")[-1].split(" ")[:-1])
        s_num = title.split("(")[-1].split(" ")[-1].split(")")[0]
        if s_num[0] == "#":
            s_num = s_num[1:]
        if s_title[-1] == ",":
            s_title = s_title[0: -1]
        c = db.cursor()
        c.execute("SELECT `id`, `s_title` FROM {} WHERE `s_title` = LOWER('{}')".format(series_table, unfix(s_title)))
        s_id = c.fetchone()
        if s_id is None:  # Doesn't exist
            c.execute("INSERT INTO {} (`id`, `s_title`) VALUES (NULL, LOWER('{}'))".format(series_table, unfix(s_title)))
            c.execute("SELECT LAST_INSERT_ID()")
            s_id = c.fetchone()[0]
        else:  # Exists
            s_id = s_id[0]
        print("I'm number {} in the series '{}'".format(s_num, unfix(title)))
    else:
        c.execute("INSERT INTO {} (`id`, `s_title`) VALUES (NULL, LOWER('{}'))".format(series_table, unfix(title)))
        c.execute("SELECT LAST_INSERT_ID()")
        s_id = c.fetchone()[0]
        print("I'm not a part of a series")

    c.execute("INSERT INTO `" + books_table + "` " +
              "(`id`, `title`, `image_url`, `small_image_url`, `year`, `month`, `day`, `gr_id`, `w_id`," +
              " `timestamp_added`, `rating`, `isbn_13`) " +
              "VALUES (NULL, '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', UNIX_TIMESTAMP(), '{}', '{}')".format(
                  unfix(b_title),
                  image_url,
                  small_image_url,
                  year,
                  month,
                  day,
                  bid,
                  wid,
                  rating,
                  isbn
              )
              )
    c.execute("SELECT LAST_INSERT_ID()")
    b_id = c.fetchone()[0]
    try:
        c.execute("SELECT id FROM `" + author_table + "` WHERE `gr_id` = {}".format(author_id))
        a_id = c.fetchone()[0]
        print("Author already exists, skipping")
    except TypeError:
        c.execute("INSERT INTO `" + author_table + "` (`id`, `name`, `gr_id`) VALUES (NULL, '{}', '{}')".format(author_name, author_id))
        c.execute("SELECT LAST_INSERT_ID()")
        print("Also adding new author to database")
        a_id = c.fetchone()[0]
    try:
        temp = int(s_num) + 2
    except NameError:
        s_num = 1
    c.execute("INSERT INTO `" + jnct_table + "` (`id`, `a_id`, `b_id`, `l_id`, `lang_id`, `s_id`, `s_index`) VALUES (NULL, '{}', '{}', {}, {}, {}, {})".format(a_id, b_id, 1, lang, s_id, s_num))
    db.commit()


def handle_add(search_term):
    r = requests.get(goodreads_url, {
        'key': goodreads_key,
        'q': search_term
    })
    print("Searching for: " + search_term)
    data = xmltodict.parse(r.content)
    if not int(data['GoodreadsResponse']['search']['total-results']) < 1:
        data = json.loads(json.dumps(data['GoodreadsResponse']['search']['results']['work']))
        if "id" in data:
            data = [data]
        print("This book was scanned as '{}' by '{}' - is this correct?".format(data[0]['best_book']["title"], data[0]['best_book']['author']['name']))
        print("[0] No!")
        print("[1] Yes, that is correct")
        print("[2] I want to edit the title (Useful if the GoodReads API doesn't have series numbering in the title)")
        action1 = input()
        if action1 == "1":
            print("Alright. Adding book to database")
            add_book(data[0], search_term)
        elif action1 == "2":
            print("What should the title be? (Use the following structure for numbering books: '<BOOK TITLE> (<SERIES TITLE> #<SERIES INDEX>)')")
            new_title = input()
            data[0]['best_book']['title'] = new_title
            add_book(data[0], search_term)

    else:
        print("No results")


while not should_exit:
    print()
    print("What do you want to do?")
    print("[0] Exit program")
    print("[1] Scan book")
    print("[2] Search by title")
    action = input()
    if action == "0" or action == 0:
        should_exit = True
    elif action == "1" or action == 1:
        print()
        print("Enter an ISBN")
        scan = do_scan()
        handle_add(scan)
    elif action == "2" or action == 2:
        print()
        print("Enter the title of the book")
        inp = input()
        handle_add(inp)
    else:
        print("Please choose a valid action")
