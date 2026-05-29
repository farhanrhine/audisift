import sqlite3

# Connect to database
conn = sqlite3.connect('screener.db')
cursor = conn.cursor()

# Promote recruiter@test.com to superuser
cursor.execute("UPDATE user SET is_superuser = 1 WHERE email = ?", ('recruiter@test.com',))
conn.commit()

# Verify
cursor.execute("SELECT email, is_superuser FROM user WHERE email = ?", ('recruiter@test.com',))
result = cursor.fetchone()
print(f"User: {result[0]}, Is Superuser: {result[1]}")

conn.close()
