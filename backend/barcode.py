import cv2
from pyzbar.pyzbar import decode
import pytesseract
import numpy as np
import os
from datetime import datetime
import requests
import time
import threading

# Create directory to store student photos
if not os.path.exists('student_photos'):
    os.makedirs('student_photos')

# Set Tesseract path for macOS if needed
# pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'

cap = cv2.VideoCapture(0)

print("Press 'q' to quit.")
print("Barcode scanner ready...")
print("🔗 Connecting to Flask server at http://localhost:5000")

# Flask server URLs
FLASK_SCAN_URL = "http://localhost:5000/api/student-scan"
FLASK_FRAME_URL = "http://localhost:5000/api/camera-frame"

# List of students in the class
STUDENT_NAMES = [
    "Rikhil Damarla",
    "Pranati Alladi",
    "Aditya Anirudh",
    "Dheeksha Baskaran",
    "Rishab Burli",
    "Ryan Chakravarthy",
    "Giulia Beatriz Colaco Silva",
    "Ryan Fu",
    "Akshaan Garg",
    "Rohan Garg",
    "Jonathan He",
    "Anya Jain",
    "Aditya Kamath",
    "Shravani Kurapati",
    "Diego Laredo",
    "Cindy Long",
    "Leela Mallya",
    "Utsav Manpuria",
    "Advika Modi",
    "Abhishek More",
    "Harshith Mummidivarapu",
    "Veer Nanda",
    "Mihir Rao",
    "Atishay Sati",
    "Gurchit Singh",
    "Alice Su",
    "Aarush Tahiliani",
    "Kevin Tam",
    "Raja Varenya Telikicherla",
    "Kavya Vijayabaskar",
    "Nivedita Warrier",
    "Parth Yadav"
]

last_barcode_data = None
last_student_name = None
last_scan_time = 0
SCAN_COOLDOWN = 3  # Seconds between scans of the same student

# Track which students have already been scanned locally
scanned_students = set()


def send_frame_to_flask(frame):
    """Send camera frame to Flask server in a separate thread"""
    try:
        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        # Send to Flask
        requests.post(
            FLASK_FRAME_URL,
            data=buffer.tobytes(),
            headers={'Content-Type': 'image/jpeg'},
            timeout=0.5
        )
    except:
        pass  # Silently fail if server is not available


def send_to_flask(student_name, student_id):
    """Send student data to Flask server"""
    try:
        response = requests.post(
            FLASK_SCAN_URL,
            json={
                'studentName': student_name,
                'studentId': student_id
            },
            timeout=2
        )
        if response.status_code == 200:
            print(f"✅ Sent to React: {student_name} - {student_id}")
            scanned_students.add(student_name)  # Track locally
            return True
        elif response.status_code == 400:
            # Check if it was rejected as duplicate
            try:
                data = response.json()
                if data.get('alreadyScanned'):
                    print(f"⚠️ Student already scanned: {student_name}")
                    scanned_students.add(student_name)  # Track locally
                else:
                    print(f"⚠️ Flask server error: {data.get('message', 'Unknown error')}")
            except:
                print(f"⚠️ Flask server error: {response.status_code}")
            return False
        else:
            print(f"⚠️ Flask server error: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Flask server. Make sure server.py is running!")
        return False
    except Exception as e:
        print(f"❌ Error sending to Flask: {str(e)}")
        return False


def extract_student_name(frame):
    """Extract student name from the ID card using OCR and match with student list"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    text = pytesseract.image_to_string(gray, config='--psm 6')

    print(f"DEBUG - Raw OCR text: {text}")
    
    text_lower = text.lower()
    
    for student_name in STUDENT_NAMES:
        student_lower = student_name.lower()
        name_parts = student_lower.split()
        all_parts_found = all(part in text_lower for part in name_parts if len(part) >= 3)
        
        if all_parts_found:
            return student_name
    
    return "Unknown Student"


def detect_student_photo(frame):
    """Detect the student photo rectangle with blue corners"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([100, 100, 100])
    upper_blue = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    for contour in contours:
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            if 50 < w < frame.shape[1] * 0.5 and 50 < h < frame.shape[0] * 0.5:
                return (x, y, w, h)

    return None


# Frame counter for throttling camera feed
frame_counter = 0

# ---------------- MAIN LOOP ----------------
while True:
    ret, frame = cap.read()
    if not ret:
        break

    barcodes = decode(frame)
    photo_rect = detect_student_photo(frame)

    if photo_rect:
        px, py, pw, ph = photo_rect
        cv2.rectangle(frame, (px, py), (px + pw, py + ph), (255, 0, 255), 2)
        cv2.putText(frame, "Photo", (px, py - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

    for barcode in barcodes:
        barcode_data = barcode.data.decode('utf-8')
        student_name = extract_student_name(frame)
        current_time = time.time()
        
        # Check if student has already been scanned
        already_scanned = student_name in scanned_students

        # Draw barcode rectangle with appropriate color
        x, y, w, h = barcode.rect
        
        if already_scanned:
            # Orange/yellow for already scanned
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 2)
            cv2.putText(frame, f"{student_name} (ALREADY SCANNED)", (x, y - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            cv2.putText(frame, f"ID: {barcode_data}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
        else:
            # Check if this is a new scan (cooldown period)
            if (student_name != last_student_name or 
                current_time - last_scan_time > SCAN_COOLDOWN):
                
                print(f"\n📋 ID: {barcode_data}")
                print(f"👤 Student Name: {student_name}")

                # Send to Flask server (and thus to React)
                if student_name in STUDENT_NAMES:
                    send_to_flask(student_name, barcode_data)
                    print(f"📊 Total unique students scanned: {len(scanned_students)}\n")
                
                last_barcode_data = barcode_data
                last_student_name = student_name
                last_scan_time = current_time

                # Save photo if detected
                if photo_rect:
                    px, py, pw, ph = photo_rect
                    photo_crop = frame[py:py+ph, px:px+pw]
                    safe_name = student_name.replace(" ", "_")
                    filename = f"student_photos/{barcode_data.replace(' ', '_')}_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    cv2.imwrite(filename, photo_crop)
                    print(f"📸 Saved student photo: {filename}")

            # Green for new students
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, student_name, (x, y - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"ID: {barcode_data}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Display info on screen
    if last_student_name:
        cv2.putText(frame, f"Last scanned: {last_student_name}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, f"ID: {last_barcode_data}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
    
    # Display unique student count
    cv2.putText(frame, f"Unique students: {len(scanned_students)}", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    # Send camera frame to Flask (throttled to every 3rd frame for performance)
    frame_counter += 1
    if frame_counter % 3 == 0:
        threading.Thread(target=send_frame_to_flask, args=(frame.copy(),), daemon=True).start()

    cv2.imshow("Barcode Scanner", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print(f"\n📊 Session complete. Total unique students scanned: {len(scanned_students)}")