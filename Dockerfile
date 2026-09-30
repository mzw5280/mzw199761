FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "bot.py"]