import React, { useState, useRef, useEffect } from 'react';
import { Plus, Trash2, GripVertical, Camera } from 'lucide-react';
import './App.css';

function App() {
  const [classrooms, setClassrooms] = useState([]);
  const [activeClassroom, setActiveClassroom] = useState(null);
  const [showNewClassroomModal, setShowNewClassroomModal] = useState(false);
  const [newClassroomName, setNewClassroomName] = useState('');
  const [newClassroomDesks, setNewClassroomDesks] = useState(10);
  const [draggedDesk, setDraggedDesk] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [cameraFeed, setCameraFeed] = useState(null);
  const [lastScanned, setLastScanned] = useState(null);
  const [scannerStatus, setScannerStatus] = useState('disconnected');
  const canvasRef = useRef(null);

  // Create a new classroom
  const createClassroom = () => {
    if (!newClassroomName.trim()) return;
    
    const desks = [];
    const groupsOfFive = Math.ceil(newClassroomDesks / 5);
    const radius = 200;
    
    for (let group = 0; group < groupsOfFive; group++) {
      const desksInGroup = Math.min(5, newClassroomDesks - group * 5);
      const angle = (2 * Math.PI * group) / groupsOfFive;
      const groupX = 400 + radius * Math.cos(angle);
      const groupY = 300 + radius * Math.sin(angle);
      
      for (let i = 0; i < desksInGroup; i++) {
        desks.push({
          id: `desk-${group}-${i}`,
          x: groupX + (i % 2) * 80 - 40,
          y: groupY + Math.floor(i / 2) * 80,
          studentName: null,
          studentId: null
        });
      }
    }
    
    const newClassroom = {
      id: Date.now(),
      name: newClassroomName,
      desks: desks
    };
    
    setClassrooms([...classrooms, newClassroom]);
    setActiveClassroom(newClassroom.id);
    setNewClassroomName('');
    setNewClassroomDesks(10);
    setShowNewClassroomModal(false);
  };

  // Add a single desk to active classroom
  const addDesk = () => {
    if (!activeClassroom) return;
    
    setClassrooms(classrooms.map(classroom => {
      if (classroom.id === activeClassroom) {
        const newDesk = {
          id: `desk-${Date.now()}`,
          x: 100,
          y: 100,
          studentName: null,
          studentId: null
        };
        return { ...classroom, desks: [...classroom.desks, newDesk] };
      }
      return classroom;
    }));
  };

  // Delete a desk
  const deleteDesk = (deskId) => {
    setClassrooms(classrooms.map(classroom => {
      if (classroom.id === activeClassroom) {
        return {
          ...classroom,
          desks: classroom.desks.filter(desk => desk.id !== deskId)
        };
      }
      return classroom;
    }));
  };

  // Handle drag start
  const handleDeskMouseDown = (e, desk) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    setDragOffset({
      x: e.clientX - rect.left - desk.x,
      y: e.clientY - rect.top - desk.y
    });
    setDraggedDesk(desk.id);
  };

  // Handle drag move
  const handleMouseMove = (e) => {
    if (!draggedDesk || !activeClassroom) return;
    
    const rect = canvasRef.current.getBoundingClientRect();
    const newX = e.clientX - rect.left - dragOffset.x;
    const newY = e.clientY - rect.top - dragOffset.y;
    
    setClassrooms(classrooms.map(classroom => {
      if (classroom.id === activeClassroom) {
        return {
          ...classroom,
          desks: classroom.desks.map(desk => 
            desk.id === draggedDesk 
              ? { ...desk, x: Math.max(0, Math.min(750, newX)), y: Math.max(0, Math.min(550, newY)) }
              : desk
          )
        };
      }
      return classroom;
    }));
  };

  // Handle drag end
  const handleMouseUp = () => {
    setDraggedDesk(null);
  };

  // Poll Flask server for new student scans AND camera feed
  useEffect(() => {
    // Poll for student scans
    const scanPollInterval = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:5000/api/get-latest-scan');
        
        // Accept both 200 (data available) and 204 (no data) as "connected"
        if (response.ok) {
          setScannerStatus('connected');
          
          // Only process data if status is 200
          if (response.status === 200) {
            const result = await response.json();
            
            if (result.success && result.data) {
              const { studentName, studentId } = result.data;
              
              console.log('Received scan:', studentName, studentId);
              setLastScanned({ studentName, studentId, time: new Date() });
              
              if (activeClassroom) {
                setClassrooms(prevClassrooms => {
                  const updatedClassrooms = prevClassrooms.map(classroom => {
                    if (classroom.id === activeClassroom) {
                      // Check if student already assigned
                      const alreadyAssigned = classroom.desks.some(
                        desk => desk.studentId === studentId
                      );
                      
                      if (alreadyAssigned) {
                        console.log(`Student ${studentName} already assigned`);
                        return classroom;
                      }
                      
                      // Find first empty desk
                      const emptyDesk = classroom.desks.find(desk => !desk.studentName);
                      
                      if (emptyDesk) {
                        console.log(`Assigning ${studentName} to desk ${emptyDesk.id}`);
                        return {
                          ...classroom,
                          desks: classroom.desks.map(desk => 
                            desk.id === emptyDesk.id 
                              ? { ...desk, studentName, studentId }
                              : desk
                          )
                        };
                      } else {
                        console.log('No empty desks available');
                      }
                    }
                    return classroom;
                  });
                  return updatedClassrooms;
                });
              } else {
                console.log('No active classroom selected');
              }
            }
          }
        } else {
          setScannerStatus('disconnected');
        }
      } catch (error) {
        console.error('Scan poll error:', error);
        setScannerStatus('disconnected');
      }
    }, 500); // Poll every 500ms for faster response

    // Poll for camera feed
    const cameraPollInterval = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:5000/api/camera-feed');
        if (response.ok && response.status === 200) {
          const blob = await response.blob();
          const imageUrl = URL.createObjectURL(blob);
          
          // Revoke old URL to prevent memory leaks
          setCameraFeed(prevFeed => {
            if (prevFeed) {
              URL.revokeObjectURL(prevFeed);
            }
            return imageUrl;
          });
        }
      } catch (error) {
        // Camera feed not available
      }
    }, 100); // Update camera feed 10 times per second

    return () => {
      clearInterval(scanPollInterval);
      clearInterval(cameraPollInterval);
      if (cameraFeed) {
        URL.revokeObjectURL(cameraFeed);
      }
    };
  }, [activeClassroom]);

  // Simulate receiving data from Python script (for testing)
  const simulateStudentScan = () => {
    if (!activeClassroom) {
      alert('Please select or create a classroom first');
      return;
    }
    
    const classroom = classrooms.find(c => c.id === activeClassroom);
    const emptyDesk = classroom?.desks.find(desk => !desk.studentName);
    
    if (emptyDesk) {
      const sampleNames = ["Rikhil Damarla", "Pranati Alladi", "Aditya Anirudh"];
      const randomName = sampleNames[Math.floor(Math.random() * sampleNames.length)];
      const randomId = `ID${Math.floor(Math.random() * 10000)}`;
      
      console.log('Test scan:', randomName, randomId);
      setLastScanned({ studentName: randomName, studentId: randomId, time: new Date() });
      
      setClassrooms(classrooms.map(classroom => {
        if (classroom.id === activeClassroom) {
          return {
            ...classroom,
            desks: classroom.desks.map(desk => 
              desk.id === emptyDesk.id 
                ? { ...desk, studentName: randomName, studentId: randomId }
                : desk
            )
          };
        }
        return classroom;
      }));
    } else {
      alert('No empty desks available');
    }
  };

  const activeClassroomData = classrooms.find(c => c.id === activeClassroom);

  return (
    <div className="attendance-tracker">
      {/* Header */}
      <header className="header">
        <h1 className="header-title">Attendance Tracker Tool</h1>
        <div className="header-status">
          <div className={`status-indicator ${scannerStatus}`}>
            <div className="status-dot"></div>
            <span>{scannerStatus === 'connected' ? 'Scanner Connected' : 'Scanner Disconnected'}</span>
          </div>
        </div>
      </header>

      <div className="main-container">
        {/* Left Sidebar - Classroom Management */}
        <div className="sidebar sidebar-left">
          <h2 className="sidebar-title">Classrooms</h2>
          
          <button onClick={() => setShowNewClassroomModal(true)} className="btn btn-primary">
            <Plus size={20} />
            New Classroom
          </button>

          {classrooms.length > 0 && (
            <select
              value={activeClassroom || ''}
              onChange={(e) => setActiveClassroom(Number(e.target.value))}
              className="classroom-select"
            >
              <option value="">Select Classroom</option>
              {classrooms.map(classroom => (
                <option key={classroom.id} value={classroom.id}>
                  {classroom.name} ({classroom.desks.length} desks)
                </option>
              ))}
            </select>
          )}

          {activeClassroomData && (
            <div className="classroom-stats">
              <p className="stats-title">Current Classroom:</p>
              <p>{activeClassroomData.name}</p>
              <p>Total Desks: {activeClassroomData.desks.length}</p>
              <p>Occupied: {activeClassroomData.desks.filter(d => d.studentName).length}</p>
            </div>
          )}

          {/* Camera Feed */}
          <div className="camera-section">
            <h3 className="camera-title">
              <Camera size={16} />
              Live Camera Feed
            </h3>
            <div className="camera-feed">
              {cameraFeed ? (
                <img src={cameraFeed} alt="Camera feed" className="camera-image" />
              ) : (
                <div className="camera-placeholder">
                  <Camera size={48} />
                  <p>No camera feed</p>
                  <p className="camera-hint">Waiting for camera...</p>
                </div>
              )}
            </div>
          </div>

          {/* Last Scanned Info */}
          {lastScanned && (
            <div className="last-scanned">
              <h3 className="last-scanned-title">Last Scanned:</h3>
              <p className="scanned-name">{lastScanned.studentName}</p>
              <p className="scanned-id">{lastScanned.studentId}</p>
              <p className="scanned-time">
                {lastScanned.time.toLocaleTimeString()}
              </p>
            </div>
          )}

          <button onClick={simulateStudentScan} className="btn btn-test">
            Test Scan
          </button>
        </div>

        {/* Main Canvas Area */}
        <div className="canvas-container">
          {activeClassroomData ? (
            <div
              ref={canvasRef}
              className="canvas"
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {activeClassroomData.desks.map(desk => (
                <div
                  key={desk.id}
                  className={`desk ${desk.studentName ? 'desk-occupied' : 'desk-empty'}`}
                  style={{ left: desk.x, top: desk.y }}
                  onMouseDown={(e) => handleDeskMouseDown(e, desk)}
                >
                  <div className="desk-grip">
                    <GripVertical size={16} />
                  </div>
                  <button onClick={() => deleteDesk(desk.id)} className="desk-delete">
                    <Trash2 size={14} />
                  </button>
                  
                  {desk.studentName ? (
                    <>
                      <p className="desk-name">{desk.studentName}</p>
                      <p className="desk-id">{desk.studentId}</p>
                    </>
                  ) : (
                    <p className="desk-empty-label">Empty Desk</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="canvas-empty">
              Create or select a classroom to begin
            </div>
          )}
        </div>

        {/* Right Sidebar - Desk Controls */}
        <div className="sidebar sidebar-right">
          <h2 className="sidebar-title">Desk Controls</h2>
          
          <button
            onClick={addDesk}
            disabled={!activeClassroom}
            className="btn btn-primary"
          >
            <Plus size={20} />
            Add Desk
          </button>

          <div className="instructions">
            <p className="instructions-title">Instructions:</p>
            <ul className="instructions-list">
              <li>Drag desks to reposition</li>
              <li>Click trash icon to delete</li>
              <li>Green desks are occupied</li>
              <li>Purple desks are empty</li>
              <li>Scan student IDs automatically</li>
            </ul>
          </div>
        </div>
      </div>

      {/* New Classroom Modal */}
      {showNewClassroomModal && (
        <div className="modal-overlay">
          <div className="modal">
            <h3 className="modal-title">Create New Classroom</h3>
            
            <div className="form-group">
              <label className="form-label">Classroom Name</label>
              <input
                type="text"
                value={newClassroomName}
                onChange={(e) => setNewClassroomName(e.target.value)}
                className="form-input"
                placeholder="e.g., Period 1 Math"
              />
            </div>
            
            <div className="form-group">
              <label className="form-label">Number of Desks</label>
              <input
                type="number"
                value={newClassroomDesks}
                onChange={(e) => setNewClassroomDesks(Math.max(1, Math.min(50, Number(e.target.value))))}
                className="form-input"
                min="1"
                max="50"
              />
              <p className="form-hint">Desks will be arranged in groups of 5</p>
            </div>
            
            <div className="modal-actions">
              <button onClick={createClassroom} className="btn btn-primary">
                Create
              </button>
              <button onClick={() => setShowNewClassroomModal(false)} className="btn btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;