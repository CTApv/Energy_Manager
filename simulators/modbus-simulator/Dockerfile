FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "pymodbus>=3.8,<3.12"
COPY simulator.py .
EXPOSE 5020 18090
CMD ["python", "simulator.py"]
