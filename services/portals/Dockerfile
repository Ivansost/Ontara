FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8002
WORKDIR /app
COPY services/portals/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/portals/ontara_portals ./ontara_portals
RUN useradd --create-home --uid 10001 portal
USER portal
EXPOSE 8002
CMD ["python", "-m", "ontara_portals"]
