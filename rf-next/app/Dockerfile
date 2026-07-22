FROM alpine:latest
RUN apk add --no-cache python3 py3-pillow tesseract-ocr tesseract-ocr-data-eng && mkdir /data
WORKDIR /app
COPY index.html server.py karvalho-logo.png rfnext-game-data.sqlite market-template.csv ./
VOLUME /data
EXPOSE 80
CMD ["python3", "server.py"]
