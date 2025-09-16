from AO3 import Session, Work

# Replace with your actual info
username = "willowphile"
password = "willow410"
work_id = 65882953  # Replace with a known work ID

# Create session and load work
session = Session(username, password)
work = Work(work_id, session)
work.load_chapters()

# Print basic info
print(f"Title: {work.title}")
print(f"Author(s): {work.authors}")
print(f"Words: {work.words}")
print(f"Summary: {work.summary}")
print(f"Summary: {work.text}")

# Save to file
#with open(f"{work.title}.html", "w", encoding="utf-8") as f:
#    f.write(work.)

work.download_to_file(f"{work.title}.html","HTML")
print("Downloaded successfully!")
