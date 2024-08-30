import streamlit as st
import json
from PIL import Image, ImageDraw, ImageFont
import io
import google.generativeai as genai
import random
import os
from google.api_core.exceptions import GoogleAPIError

def resize_image(image, max_size=800):
    """
    Resize the image maintaining the aspect ratio. If either dimension exceeds max_size, scale it down.
    """
    width, height = image.size
    if width > height:
        if width > max_size:
            height = int((height * max_size) / width)
            width = max_size
    else:
        if height > max_size:
            width = int((width * max_size) / height)
            height = max_size
    return image.resize((width, height))

def generate_random_color():
    """
    Generate a random color in hexadecimal format.
    """
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

def get_font(size=20):
    """
    Get a font object for drawing text. Attempts to load NotoSansCJK-Regular.ttc.
    Falls back to default font if unavailable.
    """
    font_files = ["NotoSansCJK-Regular.ttc"]
    
    for font_file in font_files:
        if os.path.exists(font_file):
            try:
                return ImageFont.truetype(font_file, size)
            except IOError:
                continue
    
    return ImageFont.load_default()

def draw_text_with_outline(draw, text, position, font, text_color, outline_color):
    """
    Draw text with an outline on the image.
    """
    x, y = position
    # Draw outline
    draw.text((x-1, y-1), text, font=font, fill=outline_color)
    draw.text((x+1, y-1), text, font=font, fill=outline_color)
    draw.text((x-1, y+1), text, font=font, fill=outline_color)
    draw.text((x+1, y+1), text, font=font, fill=outline_color)
    # Draw text
    draw.text(position, text, font=font, fill=text_color)

def draw_bounding_boxes(image, bboxes):
    """
    Draw bounding boxes on the image using the coordinates provided in the bboxes dictionary.
    """
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    font = get_font(20)
    
    for label, bbox in bboxes.items():
        color = generate_random_color()
        ymin, xmin, ymax, xmax = [coord / 1000 * dim for coord, dim in zip(bbox, [height, width, height, width])]
        
        draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=3)
        
        # Calculate the area needed for the label and add padding
        label_bbox = font.getbbox(label)
        label_width = label_bbox[2] - label_bbox[0] + 10  # Adding padding
        label_height = label_bbox[3] - label_bbox[1] + 10  # Adding padding
        
        if xmax - xmin < label_width:
            xmax = xmin + label_width
        if ymax - ymin < label_height:
            ymax = ymin + label_height
        
        draw.rectangle([xmin, ymin, xmin + label_width, ymin + label_height], fill=color)
        draw_text_with_outline(draw, label, (xmin + 5, ymin + 5), font, text_color="white", outline_color="black")  # Adding black outline to white text
    return image

def extract_bounding_boxes(text):
    """
    Extract bounding boxes from the given text, which is expected to be in JSON format.
    """
    try:
        bboxes = json.loads(text)
        return bboxes
    except json.JSONDecodeError:
        import re
        pattern = r'"([^"]+)":\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]'
        matches = re.findall(pattern, text)
        return {label: list(map(int, coords)) for label, *coords in matches}

def main():
    st.title("Bounding with Gemini")

    with st.sidebar:
        st.header("Gemini API Configuration")
        # Keep the input box for API key
        api_key = st.text_input("Enter your Gemini API key", type="password", value=st.session_state.get('api_key', ''))
        
        if api_key:
            st.session_state['api_key'] = api_key
            genai.configure(api_key=api_key)
            st.success("API key configured!")
        else:
            st.warning("Please enter your Gemini API key to use the app.")

    model_options = {
        "gemini-1.5-pro-exp-0827": "gemini-1.5-pro-exp-0827",
        "gemini-1.5-pro": "gemini-1.5-pro",
        "gemini-1.5-flash-exp-0827": "gemini-1.5-flash-exp-0827",
        "gemini-1.5-flash-8b-exp-0827": "gemini-1.5-flash-8b-exp-0827"
    }
    selected_model = st.selectbox("Select Gemini Model", options=list(model_options.keys()), format_func=lambda x: model_options[x])

    uploaded_file = st.file_uploader("Choose an image file", type=["jpg", "jpeg", "png"])
    
    prompt = st.text_area("Enter prompt for Gemini API", "Return bounding boxes as JSON arrays as name of object and its bounding boxes [ymin, xmin, ymax, xmax]. like 'name_1':  [ymin, xmin, ymax, xmax]")

    if st.button("Process") and uploaded_file is not None and api_key:
        try:
            # Validate and open the uploaded image file
            try:
                original_image = Image.open(uploaded_file)
            except IOError:
                st.error("Uploaded file is not a valid image. Please upload a JPG, JPEG, or PNG file.")
                return
            
            resized_image = resize_image(original_image)
            
            model = genai.GenerativeModel(selected_model)
            
            with st.spinner("Processing the image..."):
                try:
                    response = model.generate_content([prompt, resized_image])
                except GoogleAPIError as api_error:
                    st.error(f"API request failed: {api_error.message}")
                    return
            
            bboxes = extract_bounding_boxes(response.text)
            if bboxes:
                image_with_boxes = draw_bounding_boxes(resized_image.copy(), bboxes)
                
                # Display the image with bounding boxes first
                st.image(image_with_boxes, caption="Image with Bounding Boxes", use_column_width=True)
                
                # Display the API response below the image
                st.subheader("Gemini API Response")
                st.write(response.text)
                
                buffered = io.BytesIO()
                image_with_boxes.save(buffered, format="PNG")
                st.download_button(
                    label="Download Image with Bounding Boxes",
                    data=buffered.getvalue(),
                    file_name="image_with_bounding_boxes.png",
                    mime="image/png"
                )
            else:
                st.warning("No valid bounding box coordinates found in the response.")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
    elif not api_key:
        st.info("Please enter your Gemini API key in the sidebar to proceed.")

if __name__ == "__main__":
    main()
