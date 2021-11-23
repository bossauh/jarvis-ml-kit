import datetime
import string
import time
from functools import wraps
from typing import Any, Callable, Union

from flask import Flask, request
from fluxhelper import generateId
from fluxhelper.flask import makeResponse
from pymongo.database import Database
from schema import Schema
from library.utilities import schemaCheck


class APISecurity:
    """
    Class that deals with API keys.

    Parameters
    ----------
    `app` : Flask
        The flask app to apply the API security to.
    `db` : Database
        The pymongo or pymongo-like database to use for storing credentials.

    -- Non required --
    `refreshRate` : float
        In order to prevent spamming the database with requests, we can set a refresh rate to refresh the cached keys every x seconds.
    `keyHolder` : str
        The name of the key that holds the API key. Keep in mind this uses json.
    `keyDictionary` : str
        A string containing characters to use for generating new API keys.
    `keyLength` : int
        Length of API keys.
    """

    def __init__(self, app: Flask, db: Database, **kwargs) -> None:
        self.app = app
        self.db = db

        self.refreshRate = kwargs.get("refreshRate", 5.0)
        self.keyHolder = kwargs.get("keyHolder", "__key__")
        self.keyDictionary = kwargs.get(
            "keyDictionary", string.ascii_letters + string.digits + "-.,;")
        self.keyLength = kwargs.get("keyLength", 50)

        self.keys = []
        self.lastRefresh = None

    def patch(self) -> None:
        """Patch flask's before_request. Must be called."""
        @self.app.before_request
        async def beforeRequest():
            data = request.json
            if data:
                key = data.pop("__key__", None)
                if key:
                    if await self.validateKey(key):
                        return

            return makeResponse(status=401, msg="unauthorized")

    def generateKey(self) -> str:
        key = generateId(self.keyLength, self.keyDictionary)
        self.db.keys.insert_one({
            "key": key,
            "active": True,
            "created": datetime.datetime.now()})
        
        return key

    def revokeKey(self, key: str) -> str:
        if not self.db.keys.count_documents({"key": key, "active": True}):
            raise ValueError(f"{key} not found")
        
        self.db.keys.update_one({"key": key}, {"$set": {"active": True}})
        return key

    async def refreshKeys(self) -> None:
        if self.lastRefresh is not None:
            if not((time.time() - self.lastRefresh) >= self.refreshRate):
                return

        self.keys = list(self.db.keys.find({"active": True}))
        self.lastRefresh = time.time()

    async def validateKey(self, key: str) -> bool:
        await self.refreshKeys()
        queried = [x for x in self.keys if x["key"] == key]

        if queried:
            return True
        return False


class RateLimiter:
    """
    Class that handles rate limiting.

    Parameters
    ----------
    `key` : Union[Callable, str]
        Key to use, if provided a string, it would treat that string as if it's a key inside request.json.
    """

    def __init__(self, key: Union[Callable, str] = None) -> None:

        self.key = key
        if not self.key:
            self.key = self.getRemoteAddr

        self.requests = {}

    def getRemoteAddr(self) -> str:
        return request.remote_addr

    def getKey(self) -> Any:
        if isinstance(self.key, str):
            data = request.json
            return data[self.key]
        return self.key()

    def limit(self, count: int, returnFunction: callable = None, key: Union[Callable, str] = None) -> None:
        """Rate limit a route using seconds, e.g., 5 per second, 2 per second."""

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):

                key_ = None

                try:
                    if isinstance(key, str):
                        key_ = request.json[key]
                    else:
                        if key is None:
                            key_ = self.getKey()
                        else:
                            key_ = key()
                # Catch reasonable exceptions you'd get when trying to get a key then default back to self.getKey()
                except (KeyError, IndexError, ValueError, AttributeError):
                    key_ = self.getKey()

                prevRequest = self.requests.get(key_)
                self.requests[key_] = time.time()

                if prevRequest:
                    if (time.time() - prevRequest) < (1 / count):
                        if returnFunction:
                            return returnFunction()
                        return makeResponse(status=429, msg="rate limit in place")

                return await func(*args, **kwargs)
            return wrapper
        return decorator


class RouteValidator:
    """
    Validates the json content of a request using the schema library.

    Parameters
    ----------
    `handler` : Callable
        Function to call if validating failed. Defaults to self.defaultHandler
    """

    def __init__(self, handler: Callable = None) -> None:
        self.handler = handler if handler else self.defaultHandler
    
    def defaultHandler(self) -> None:
        return makeResponse(status=400, msg="incorrectly structured data")
    
    def validate(self, schema: Schema) -> None:
        """Validate a route's json data."""

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                data = request.json
                if schemaCheck(schema, data):
                    return await func(*args, **kwargs)

                return self.handler()
            return wrapper
        return decorator
