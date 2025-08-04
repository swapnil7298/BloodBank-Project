print("--- Test script is starting up. ---")

try:
    from flask import Flask
    print("--- Flask library was found successfully. ---")
except ImportError:
    print("!!! FLASK NOT FOUND. Please run 'pip install Flask' in your terminal and try again. !!!")
    exit() # Stop the script if flask is not installed

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '<h1>Success! The test server is running.</h1>'

print("--- Everything looks OK. Starting the server... ---")
app.run(debug=True)