# import os
# import base64
# import numpy as np
# import cv2
# from tensorflow.keras.models import load_model
# import requests
# import mediapipe as mp
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from collections import Counter
# import google.generativeai as genai

# # Initialize MediaPipe models
# mp_holistic = mp.solutions.holistic
# mp_drawing = mp.solutions.drawing_utils

# # Load trained model
# MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'final_action.h5')
# model = load_model(MODEL_PATH)

# # Create tmp directory if it doesn't exist
# if not os.path.exists('tmp'):
#     os.makedirs('tmp')

# # Gemini API setup
# genai.configure(api_key='AIzaSyCqDBN9dNuBfe3mtHgtFW7Gopi1qOS_78c')

# # Actions
# actions = np.array(['are you free today', 'can i help you', 'congradulations', 'do me a favour',
#                     'do not be stubborn', 'do not worry', 'do you need something', 'go and sleep',
#                     'had your food', 'help me', 'hi how are you', 'i am not really sure',
#                     'i am really grateful', 'i do not agree', 'i really appreciate it',
#                     'take care of yourself', 'tell me truth', 'thank you so much',
#                     'that is so kind of you', 'what are you doing'])
# label_map = {label: num for num, label in enumerate(actions)}

# # Video Upload and Action Prediction API
# class VideoUploadView(APIView):
#     def post(self, request):
#         video_data = request.data.getlist('videos')  # Get list of base64-encoded videos
#         individual_predictions = []

#         for index, base64_video in enumerate(video_data):
#             # Decode the base64 video data to binary
#             video_binary = base64.b64decode(base64_video.split(",")[1])  # Remove the `data:video/mp4;base64,` prefix

#             # Save binary data to a temporary file
#             video_path = f'tmp/video_{index}.mp4'
#             with open(video_path, 'wb') as video_file:
#                 video_file.write(video_binary)

#             # Process the video
#             cap = cv2.VideoCapture(video_path)

#             with mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5) as holistic:
#                 sequence = []
#                 predictions_with_confidence = []
#                 threshold = 0.65

#                 while cap.isOpened():
#                     ret, frame = cap.read()
#                     if not ret:
#                         break

#                     frame = cv2.resize(frame, (640, 480))
#                     image, results = mediapipe_detection(frame, holistic)
#                     keypoints = extract_keypoints(results)
#                     sequence.append(keypoints)
#                     sequence = sequence[-30:]

#                     if len(sequence) == 30:
#                         res = model.predict(np.expand_dims(sequence, axis=0))[0]
#                         prediction_index = np.argmax(res)
#                         confidence = res[prediction_index]
#                         predicted_action = actions[prediction_index] if confidence > threshold else "No Action"
#                         predictions_with_confidence.append({'action': predicted_action, 'confidence': confidence})

#             cap.release()

#             # Get final prediction for the video
#             final_prediction = get_final_prediction(predictions_with_confidence, window_size=15)
#             individual_predictions.append(final_prediction)

#         # Combine predictions and rephrase with Gemini API
#         combined_sentence = ", ".join(individual_predictions)
#         rephrased_sentence = send_to_gemini(combined_sentence)

#         return Response({'final_rephrased_sentence': rephrased_sentence})
import os
import numpy as np
import cv2  # Use OpenCV to process video
from tensorflow.keras.models import load_model
import requests
import mediapipe as mp
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from .forms import VideoUploadForm
from collections import Counter
import google.generativeai as genai

# Initialize MediaPipe models
mp_holistic = mp.solutions.holistic  # Holistic model
mp_drawing = mp.solutions.drawing_utils  # Drawing utilities

# Load trained model
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'final_action.h5')
model = load_model(MODEL_PATH)

# Create tmp directory if it doesn't exist
if not os.path.exists('tmp'):
    os.makedirs('tmp')

# Gemini API setup
genai.configure(api_key='AIzaSyCqDBN9dNuBfe3mtHgtFW7Gopi1qOS_78c')


# Actions
actions = np.array(['are you free today', 'can i help you', 'congradulations', 'do me a favour',
                    'do not be stubborn', 'do not worry', 'do you need something', 'go and sleep',
                    'had your food', 'help me', 'hi how are you', 'i am not really sure',
                    'i am really grateful', 'i do not agree', 'i really appreciate it',
                    'take care of yourself', 'tell me truth', 'thank you so much',
                    'that is so kind of you', 'what are you doing'])
label_map = {label: num for num, label in enumerate(actions)}

# Process video and predict action
def mediapipe_detection(image, model):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image.flags.writeable = False
    results = model.process(image)
    image.flags.writeable = True
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image, results

def extract_keypoints(results):
    pose = np.array([[res.x, res.y, res.z, res.visibility] for res in results.pose_landmarks.landmark]).flatten() if results.pose_landmarks else np.zeros(33 * 4)
    face = np.array([[res.x, res.y, res.z] for res in results.face_landmarks.landmark]).flatten() if results.face_landmarks else np.zeros(468 * 3)
    lh = np.array([[res.x, res.y, res.z] for res in results.left_hand_landmarks.landmark]).flatten() if results.left_hand_landmarks else np.zeros(21 * 3)
    rh = np.array([[res.x, res.y, res.z] for res in results.right_hand_landmarks.landmark]).flatten() if results.right_hand_landmarks else np.zeros(21 * 3)
    return np.concatenate([pose, face, lh, rh])

# Function to find the prediction with the highest confidence level
def get_final_prediction(predictions_with_confidence, window_size=15):
    # Only consider the last `window_size` predictions
    recent_predictions = predictions_with_confidence[-window_size:]
    
    # Dictionary to store weighted scores for each action
    weighted_scores = {}
    
    # Iterate over recent predictions to calculate weighted score
    for prediction in recent_predictions:
        action = prediction['action']
        confidence = prediction['confidence']
        
        # Skip "No Action" if you want to ignore it
        if action == "No Action":
            continue
        
        # Add weighted confidence to the action's total score
        if action in weighted_scores:
            weighted_scores[action] += confidence
        else:
            weighted_scores[action] = confidence

    # Find the action with the highest total weighted score
    if weighted_scores:
        final_action = max(weighted_scores, key=weighted_scores.get)
        return final_action
    else:
        return "No Action"

# Send the combined predictions to Gemini API for rephrasing
def send_to_gemini(combined_sentence):
    model = genai.GenerativeModel("gemini-1.5-pro-002")
    response = model.generate_content(f"Rephrase the following predictions into a natural sentence suitable for casual conversation: '{combined_sentence}'")
    return response.text # Return the rephrased sentence or original if the API fails

# Video Upload and Action Prediction API
class VideoUploadView(APIView):
    def post(self, request):
        video_files = request.FILES.getlist('videos')  # Get a list of all uploaded video files
        individual_predictions = []  # To store predictions for each video

        for video_file in video_files:
            video_path = f'tmp/{video_file.name}'  # Define the path to save each video

            # Save each video to the temporary directory
            with open(video_path, 'wb+') as dest:
                for chunk in video_file.chunks():
                    dest.write(chunk)

            # Open the video file
            cap = cv2.VideoCapture(video_path)

            # Set up mediapipe model
            with mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5) as holistic:
                sequence = []
                predictions_with_confidence = []  # List to store predictions along with confidence
                threshold = 0.65  # Keep the threshold at 0.65 as you have set

                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break  # Exit the loop if video ends

                    # Resize and crop the frame
                    height, width, _ = frame.shape
                    frame = cv2.resize(frame, (640, 480))

                    x_start = int(width * 0.01)  # 1% from the left
                    x_end = int(width * 0.99)    # 1% from the right
                    y_start = int(height * 0.001)  # 0.1% from the top
                    y_end = int(height * 1)   # 100% from the bottom

                    frame = frame[y_start:y_end, x_start:x_end]  # Crop the frame

                    # Make detections
                    image, results = mediapipe_detection(frame, holistic)

                    # Extract keypoints
                    keypoints = extract_keypoints(results)
                    sequence.append(keypoints)
                    sequence = sequence[-30:]  # Keep the latest 30 frames

                    if len(sequence) == 30:
                        res = model.predict(np.expand_dims(sequence, axis=0))[0]
                        prediction_index = np.argmax(res)
                        confidence = res[prediction_index]

                        # Debugging print statement for action and confidence
                        print(f"Predicted action: {actions[prediction_index]}, Confidence: {confidence:.4f}")

                        if confidence > threshold:
                            predicted_action = actions[prediction_index]
                            # Append both action and confidence
                            predictions_with_confidence.append({'action': predicted_action, 'confidence': confidence})
                        else:
                            predictions_with_confidence.append({'action': "No Action", 'confidence': confidence})

            cap.release()

            # Get the final prediction with weighted voting
            final_prediction = get_final_prediction(predictions_with_confidence, window_size=15)
            
            # Add the individual prediction to the list
            individual_predictions.append(final_prediction)

        # Combine all individual predictions into one sentence
        combined_sentence = ", ".join(individual_predictions)
        print(combined_sentence)

        # Send the combined sentence to Gemini API for rephrasing
        rephrased_sentence = send_to_gemini(combined_sentence)
        print(rephrased_sentence)

        # Return the rephrased sentence as the final output
        return Response({'final_rephrased_sentence': rephrased_sentence})
