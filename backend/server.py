from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import threading
import queue
import cv2
from pyzbar.pyzbar import decode
import pytesseract
import numpy as np
import os
from datetime import datetime
import time

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# Create directory to store student photos
if not os.path.exists('student_photos'):
    os.makedirs('student_photos')

# Queue to store scanned student data
student_queue = queue.Queue()

# Global variable to store the latest camera frame
latest_frame = None
frame_lock = threading.Lock()

# Camera scanning state
camera_running = False
camera_thread = None

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

# Scanning state
last_barcode_data = None
last_student_name = None
last_scan_time = 0
SCAN_COOLDOWN = 3  # Seconds between scans of the same student

# Track which students have already been scanned in this session
scanned_students = set()  # Set of student names that have been scanned

# Track unknown student reads per barcode ID
unknown_read_count = {}  # {barcode_id: count}
UNKNOWN_THRESHOLD = 15  # Number of failed reads before accepting as "Unknown Student"


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


def camera_scan_loop():
    """Main camera scanning loop running in background thread"""
    global latest_frame, last_barcode_data, last_student_name, last_scan_time, camera_running
    
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Cannot open camera")
        camera_running = False
        return
    
    print("📷 Camera started successfully")
    
    while camera_running:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to read frame")
            break

        # Detect barcodes
        barcodes = decode(frame)
        photo_rect = detect_student_photo(frame)

        # Draw photo rectangle if detected
        if photo_rect:
            px, py, pw, ph = photo_rect
            cv2.rectangle(frame, (px, py), (px + pw, py + ph), (255, 0, 255), 2)
            cv2.putText(frame, "Photo", (px, py - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

        # Process barcodes
        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
            student_name = extract_student_name(frame)
            current_time = time.time()

            # Check if student name is in the roster
            name_is_valid = student_name in STUDENT_NAMES
            
            # Check if this student has already been scanned
            already_scanned = student_name in scanned_students
            
            # Handle unknown students with tracking
            if not name_is_valid and student_name == "Unknown Student":
                # Initialize or increment counter for this barcode
                if barcode_data not in unknown_read_count:
                    unknown_read_count[barcode_data] = 0
                unknown_read_count[barcode_data] += 1
                
                print(f"⚠️ Unknown read #{unknown_read_count[barcode_data]} for ID: {barcode_data}")
                
                # Only proceed if we've hit the threshold
                if unknown_read_count[barcode_data] < UNKNOWN_THRESHOLD:
                    # Draw barcode but don't process
                    x, y, w, h = barcode.rect
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 2)
                    cv2.putText(frame, f"Reading... ({unknown_read_count[barcode_data]}/{UNKNOWN_THRESHOLD})", 
                               (x, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
                    cv2.putText(frame, f"ID: {barcode_data}", (x, y - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
                    continue
                else:
                    # After 15 reads, accept as unknown
                    print(f"⚠️ Accepting as Unknown Student after {UNKNOWN_THRESHOLD} attempts")
                    name_is_valid = True  # Allow it to be added
            elif name_is_valid:
                # Reset unknown counter if name was successfully read
                if barcode_data in unknown_read_count:
                    del unknown_read_count[barcode_data]

            # Draw barcode rectangle and info
            x, y, w, h = barcode.rect
            
            # Check if already scanned and show appropriate visual feedback
            if already_scanned:
                # Yellow/orange color for already scanned students
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 2)
                cv2.putText(frame, f"{student_name} (ALREADY SCANNED)", (x, y - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
                cv2.putText(frame, f"ID: {barcode_data}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            else:
                # Check if this is a new scan (cooldown period)
                if name_is_valid and (student_name != last_student_name or 
                    current_time - last_scan_time > SCAN_COOLDOWN):
                    
                    print(f"\n📋 ID: {barcode_data}")
                    print(f"👤 Student Name: {student_name}")

                    # Add to queue and mark as scanned
                    student_queue.put({
                        'studentName': student_name,
                        'studentId': barcode_data
                    })
                    scanned_students.add(student_name)  # Track this student
                    print(f"✅ Added to queue: {student_name} - {barcode_data}")
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

                # Green color for new/valid students
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, student_name, (x, y - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"ID: {barcode_data}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Draw last scanned info and total count
        if last_student_name:
            cv2.putText(frame, f"Last scanned: {last_student_name}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.putText(frame, f"ID: {last_barcode_data}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        
        # Draw total unique students scanned
        cv2.putText(frame, f"Unique students: {len(scanned_students)}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # Encode frame as JPEG and store
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        with frame_lock:
            latest_frame = buffer.tobytes()

        # Small delay to prevent excessive CPU usage
        time.sleep(0.033)  # ~30 FPS

    cap.release()
    print("📷 Camera stopped")


# Flask Routes

@app.route('/api/student-scan', methods=['POST'])
def student_scan():
    """Receive student scan data (for backward compatibility)"""
    try:
        data = request.get_json()
        student_name = data.get('studentName')
        student_id = data.get('studentId')
        
        if student_name and student_id:
            # Check if student already scanned
            if student_name in scanned_students:
                print(f"⚠️ Student already scanned: {student_name}")
                return jsonify({
                    'success': False, 
                    'message': 'Student already scanned',
                    'alreadyScanned': True
                }), 400
            
            print(f"✅ Received scan: {student_name} - {student_id}")
            student_queue.put({
                'studentName': student_name,
                'studentId': student_id
            })
            scanned_students.add(student_name)
            return jsonify({'success': True, 'message': 'Student data received'}), 200
        else:
            return jsonify({'success': False, 'message': 'Missing data'}), 400
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/camera-feed', methods=['GET'])
def get_camera_feed():
    """Send the latest camera frame to React frontend"""
    global latest_frame
    
    with frame_lock:
        if latest_frame:
            return Response(latest_frame, mimetype='image/jpeg')
        else:
            return Response(status=204)


@app.route('/api/get-latest-scan', methods=['GET'])
def get_latest_scan():
    """Poll for latest scanned student (used by React frontend)"""
    try:
        if not student_queue.empty():
            student_data = student_queue.get()
            return jsonify({
                'success': True,
                'data': student_data
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'No new scans'
            }), 204
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/camera/start', methods=['POST'])
def start_camera():
    """Start the camera scanning"""
    global camera_running, camera_thread
    
    if camera_running:
        return jsonify({'success': False, 'message': 'Camera already running'}), 400
    
    camera_running = True
    camera_thread = threading.Thread(target=camera_scan_loop, daemon=True)
    camera_thread.start()
    
    return jsonify({'success': True, 'message': 'Camera started'}), 200


@app.route('/api/camera/stop', methods=['POST'])
def stop_camera():
    """Stop the camera scanning"""
    global camera_running
    
    if not camera_running:
        return jsonify({'success': False, 'message': 'Camera not running'}), 400
    
    camera_running = False
    return jsonify({'success': True, 'message': 'Camera stopped'}), 200


@app.route('/api/camera/status', methods=['GET'])
def camera_status():
    """Get camera status"""
    return jsonify({
        'running': camera_running,
        'last_scan': {
            'name': last_student_name,
            'id': last_barcode_data
        } if last_student_name else None,
        'total_scanned': len(scanned_students),
        'scanned_students': list(scanned_students)
    }), 200


@app.route('/api/reset-scans', methods=['POST'])
def reset_scans():
    """Reset all scanned students (clear the session)"""
    global scanned_students, last_barcode_data, last_student_name, unknown_read_count
    scanned_students.clear()
    unknown_read_count.clear()
    last_barcode_data = None
    last_student_name = None
    
    # Clear the queue
    while not student_queue.empty():
        student_queue.get()
    
    print("🔄 Reset all scanned students")
    return jsonify({'success': True, 'message': 'Scan session reset'}), 200


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'running', 'message': 'Flask server is running'}), 200


if __name__ == '__main__':
    print("🚀 Flask server starting on http://localhost:5000")
    print("📡 Ready to receive barcode scans and camera feed...")
    print("📷 Camera will start automatically...")
    
    # Start camera automatically
    camera_running = True
    camera_thread = threading.Thread(target=camera_scan_loop, daemon=True)
    camera_thread.start()
    
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)