# Campus France Advisor

Campus France Advisor is a Python web application that helps students explore higher education programs in France and prepare their applications.

## Features

- Search for university programs using a local catalogue.
- Filter programs by study level and other criteria.
- Create a student profile and organize up to 7 study choices.
- Ask Gemini AI for personalized guidance.
- Review admission requirements and identify information that needs verification.

## Technologies

- Python
- Streamlit
- Pandas
- Google Gemini API
- Excel

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/SanoF404/donner_meilleuir_choix_de_fac_capmpus_france.git
   cd donner_meilleuir_choix_de_fac_capmpus_france
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:

   ```bash
   pip install streamlit pandas python-dotenv google-genai openpyxl
   ```

4. Create a `.env` file in the project folder and add your Gemini API key:

   ```text
   GEMINI_API_KEY=your_api_key_here
   ```

   Keep your API key private. Never commit your `.env` file to GitHub.

5. Start the application:

   ```bash
   python -m streamlit run app.py
   ```

## Important Notes

- Recommendations are guidance, not guarantees of admission.
- Admission requirements, tuition fees, deadlines, and language requirements must be checked on official university websites.
- The available programs depend on the local catalogue and may not represent every program in France.
- The AI assistant sends relevant profile information and selected program data to Google Gemini when the user consents.

## Project Status

This project is under development.

## Author

**SanoF404**
