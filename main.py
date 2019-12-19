import requests
import xmltodict
import json
import mysql.connector
from serial import Serial
import re

config = {}

with open('env.json') as f:
    config = json.loads(f.read())

s = Serial('COM3')

# Goodreads stuff
goodreads_key = config['goodreads_key']
goodreads_url = "https://www.goodreads.com/search/index.xml"


def do_scan():
    print("Awaiting scan...")
    return s.read(13).decode("UTF-8")


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

# Main loop
should_exit = False


def fix(s):
    buf = []

    for i in range(0, len(s)):
        if re.search("[a-zA-Z0-9\s]", s[i]):
            buf.append(s[i])
        else:
            buf.append("&#{};".format(ord(s[i])))
    return "".join(buf)


def add_book(book, isbn):
    title = fix(book['best_book']['title'])
    small_image_url = book['best_book']['small_image_url']
    image_url = small_image_url.split('._')[0] + "._SX500_." + small_image_url.split('_.')[1]
    year = book['original_publication_year']["#text"] if "@nil" not in book['original_publication_year'] else -1
    month = book['original_publication_month']["#text"] if "@nil" not in book['original_publication_month'] else -1
    day = book['original_publication_day']["#text"] if "@nil" not in book['original_publication_day'] else -1
    rating = book['average_rating']['#text'] if '#text' in book['average_rating'] else book['average_rating']
    bid = book['best_book']['id']['#text']
    wid = book['id']['#text']
    author_name = fix(book['best_book']['author']['name'])
    author_id = book['best_book']['author']['id']["#text"]
    c = db.cursor()
    c.execute("INSERT INTO `" + books_table + "` " +
              "(`id`, `title`, `image_url`, `small_image_url`, `year`, `month`, `day`, `gr_id`, `w_id`," +
              " `timestamp_added`, `rating`, `isbn_13`) " +
              "VALUES (NULL, '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', UNIX_TIMESTAMP(), '{}', '{}')".format(
                  title,
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
    c.execute("INSERT INTO `" + jnct_table + "` (`id`, `a_id`, `b_id`, `l_id`) VALUES (NULL, '{}', '{}', {})".format(a_id, b_id, 1))
    db.commit()


while not should_exit:
    print()
    print("What do you want to do?")
    print("[0] Exit program")
    print("[1] Scan book")
    action = input()
    if action == "0":
        should_exit = True
    elif action == "1":
        print()
        print("Enter an ISBN")
        scan = do_scan()
        r = requests.get(goodreads_url, {
            'key': goodreads_key,
            'q': scan
        })
        data = xmltodict.parse(r.content)
        if not int(data['GoodreadsResponse']['search']['total-results']) < 1:
            data = json.loads(json.dumps(data['GoodreadsResponse']['search']['results']['work']))
            if "id" in data:
                data = [data]
            print("This book was scanned as '{}' - is this correct?".format(data[0]['best_book']["title"]))
            print("[0] No!")
            print("[1] Yes, that is correct")
            action1 = input()
            if (action1 == "1"):
                print("Alright. Adding book to database")
                add_book(data[0], scan)
        else:
            print("No results.")

    else:
        print("Please choose a valid action")
