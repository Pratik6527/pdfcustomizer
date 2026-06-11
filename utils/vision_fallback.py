import cv2
import numpy as np

def apply_opencv_fallback(image_path, output_path):
    """
    Reads an image, isolates light-colored watermark pixels using color thresholding,
    and turns them into pure white (255, 255, 255), leaving crisp dark text completely untouched.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image for OpenCV fallback.")
        
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Identify faint/light pixels (between 180 and 245 typically)
    # The requirement: "turns them into pure white, leaving crisp dark text untouched"
    # A simple thresholding approach: anything above a certain lightness becomes white.
    # Text is usually < 100 in grayscale.
    
    # Anything lighter than 150 becomes white
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    
    # Create the output image
    # For colored text, we could use the threshold as a mask to turn those pixels white in original
    result = img.copy()
    
    # Where thresh is 255 (the background/light stuff), make the result white
    result[thresh == 255] = [255, 255, 255]
    
    cv2.imwrite(output_path, result)
    return output_path
