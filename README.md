# snapshotter-periphery-blockfetcher

## Local Testing Instructions

To set up and run the block fetcher service locally, follow these steps:

### Prerequisites

- Ensure you have Docker and Docker Compose installed on your machine.

### Setup

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd snapshotter-periphery-blockfetcher
   ```

2. **Create a `.env` File**:
   - Copy the `.env.example` file to `.env` and fill in the necessary environment variables.
   ```bash
   cp .env.example .env
   ```

3. **Build and Start the Services**:
   - Use Docker Compose to build and start the services. The `local` profile will include the Redis service for local testing.
   ```bash
   docker-compose --profile local up --build
   ```

4. **Access Logs**:
   - Logs are available in the `./logs` directory. You can also view logs in real-time using:
   ```bash
   docker-compose logs -f
   ```

5. **Shut Down the Services**:
   - To stop the services, use:
   ```bash
   docker-compose down
   ```

### Notes

- The `local` profile includes a Redis service for testing purposes. In production, ensure that your configuration points to an external Redis service.
- Ensure that all necessary environment variables are set in the `.env` file for the application to function correctly.
