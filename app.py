import datetime
import gc
import sys
import threading
import time

import click
import psutil
from flask import Flask
from fluxhelper import Database, Logger, joinPath, loadJson
from nudenet import NudeClassifier
from waitress import serve

from apis import constructNsfw
from library import APISecurity, RateLimiter, RouteValidator, utilities


class Monitor:
    """
    Class to monitor memory usages and other stuff. All data collected will be stored in the database.
    Keep in mind that this monitors the overall system not the program itself.

    Parameters
    ----------
    `db` : Database
        pymongo or pymongo-like database.
    """

    def __init__(self) -> None:

        self.monitorThread = None
        self.monitorStopped = False

    def monitor(self) -> None:
        """Start the monitor."""
        self.monitorThread = threading.Thread(
            target=self.monitor_, daemon=True)
        self.monitorThread.start()

    def stopMonitoring(self) -> None:
        """Stop the monitor."""
        self.monitorStopped = True

    def monitor_(self) -> None:
        while not self.monitorStopped:
            cpu = psutil.cpu_percent()
            virtual_memory = psutil.virtual_memory()

            data = {
                "memory": {
                    "total": virtual_memory.total / 1e+6,
                    "available": virtual_memory.available / 1e+6,
                    "used": virtual_memory.used / 1e+6,
                    "free": virtual_memory.free / 1e+6,
                    "percent": virtual_memory.percent
                },
                "cpu": {
                    "percent": cpu
                },
                "system": sys.platform,
                "datetime": datetime.datetime.now()
            }

            self.logging.debug(
                f"Memory Used: {data['memory']['used']} ({data['memory']['percent']}%) | CPU: {data['cpu']['percent']}%")

            self.db.monitoring.insert_one(data)
            time.sleep(10)


class Server(Monitor):
    def __init__(self, port: int = None, doMonitor: bool = False) -> None:
        self.logging = Logger(debug=True)
        self.app = Flask(__name__)
        self.limiter = RateLimiter()
        self.validator = RouteValidator()
        self.port = port if port else self.config["server"]["port"]
        self.doMonitor = doMonitor

        # Initialize database
        self.dbClient = Database(
            self.config["database"]["name"], connectionString=self.config["database"]["connectionString"], logging=self.logging, cacheModified=0)
        self.db = self.dbClient.db

        # Apply API security
        self.apiSecurity = APISecurity(self.app, self.db)
        self.apiSecurity.patch()

        # Register blueprints
        self.registerBlueprints()
        self.postInit()

        super().__init__()

    def postInit(self) -> None:

        x = NudeClassifier()
        del x
        gc.collect()

    def registerBlueprints(self) -> None:
        nsfw = constructNsfw(self)
        self.app.register_blueprint(nsfw)

    def run(self) -> None:
        """Run the server and also monitoring."""

        if self.doMonitor:
            self.monitor()

        if utilities.inCloud():
            self.logging.debug(
                f"In the cloud, running server using waitress on port {self.port}")
            serve(
                self.app,
                listen=f"*:{self.port}",
                trusted_proxy="*",
                trusted_proxy_headers="x-forwarded-for x-forwarded-proto x-forwarded-port",
                log_untrusted_proxy_headers=True,
                clear_untrusted_proxy_headers=True,
                threads=4
            )
        else:
            host = self.config["server"]["host"]
            self.logging.debug(
                f"In local, running server using flask app.run on port {self.port} and host {host}")
            self.app.run(host=host, port=self.port,
                         use_reloader=False, debug=True)

    @property
    def config(self) -> dict:
        return loadJson(joinPath("./config.json"))[0]


@click.command()
@click.option("--port", "-p", default=None, help="Port to use. Defaults to the port inside config.json")
@click.option("--generate_key", is_flag=True, help="Generate an api key and print it out on launch.")
@click.option("-d", is_flag=True, help="Don't launch the server. You'd normally do this if you're doing something like just generating a key.")
@click.option("-m", "--monitor", is_flag=True, help="Starts the server with monitoring enabled.")
def main(port, generate_key, d, monitor) -> None:

    server = Server(port, doMonitor=monitor)
    if generate_key:
        key = server.apiSecurity.generateKey()
        server.logging.success(f"Successfully generated API key: {key}")

    if not d:
        server.run()


if __name__ == "__main__":
    main()
