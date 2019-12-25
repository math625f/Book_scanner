import mysql.connector
import re
import json

config = {}

with open('env.json') as f:
    config = json.loads(f.read())

db = mysql.connector.connect(
    host=config['host'],
    user=config['user'],
    passwd=config['passwd'],
    database=config['database']
)

books_table = config['books_table']
jnct_table = config['jnct_table']
series_table = config['series_table']


def unfix(s):
    buf = []

    for i in range(0, len(s)):
        if re.search("[a-zA-Z0-9\s]", s[i]):
            buf.append(s[i])
        else:
            buf.append("&#{};".format(ord(s[i])))
    return "".join(buf)


def fix(str):
    return re.sub('&#(\d+);', (lambda x: chr(int(x.group(0).split("#")[1].split(";")[0]))), str)

c = db.cursor()
c.execute("SELECT {}.b_id, {}.a_id, {}.title from {}, {} WHERE {}.id = {}.b_id".format(jnct_table, jnct_table, books_table, books_table, jnct_table, books_table, jnct_table))
res = c.fetchall()
for r in res:
    b = (
        r[0], r[1], fix(r[2])
    )
    b_title = b[2].split("(")[0].strip()
    print("Book id: {}\nAuthor id: {}\nTitle: {}".format(b[0], b[1], b[2]))
    if re.search('(\(.*,?\s#?[0-9]*\))', b[2]):
        s_title = " ".join(b[2].split('(')[1].split(")")[0].split(" ")[0: -1])
        s_num = b[2].split("(")[1].split(")")[0].split(" ")[-1]
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
        print(s_id)
        c.execute("UPDATE {} SET title = '{}' WHERE id = {}".format(books_table, unfix(b_title), b[0]))
        c.execute("UPDATE {} SET s_id = {}, s_index = {} WHERE b_id = {}".format(jnct_table, s_id, s_num, b[0]))
        print("I'm number {} in the series '{}'".format(s_num, unfix(b[2])))
    else:
        c.execute("INSERT INTO {} (`id`, `s_title`) VALUES (NULL, '{}')".format(series_table, unfix(b[2])))
        c.execute("SELECT LAST_INSERT_ID()")
        s_id = c.fetchone()[0]
        c.execute("UPDATE {} SET title = LOWER('{}') WHERE id = {}".format(books_table, unfix(b_title), b[0]))
        c.execute("UPDATE {} SET s_id = {}, s_index = 1 WHERE b_id = {}".format(jnct_table, s_id, b[0]))
        print("I'm not a part of a series")
    db.commit()
    print("---------")
print(len(res))