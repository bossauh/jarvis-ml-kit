"""This NSFW detection uses the NudeNet library."""

import base64
import gc
import os
import tempfile
import ffmpy
from typing import TYPE_CHECKING

import imagehash
from flask import Blueprint, request
from fluxhelper.flask import makeResponse
from library.schemas import *
from nudenet import NudeClassifier
from PIL import Image
from videohash.videohash import VideoHash

if TYPE_CHECKING:
    from ..app import Server


def constructNsfw(server: "Server") -> Blueprint:
    app = Blueprint("nsfw_detection", __name__, url_prefix="/nsfw_detection")

    @app.route("/classify", methods=["GET"])
    @server.limiter.limit(2, key="ratelimitKey")
    @server.validator.validate(NSFW_DETECTION_CLASSIFY)
    def classify():

        """
        Classifies an image or video whether it is NSFW or not.

        Parameters
        ----------
        {
            "bytes": str,
                The content you're trying to classify that is previously bytes but has been converted to a string using \
                    >>> contentBytes = base64.b64encode(contentBytes)
                    >>> contentBytes = contentBytes.decode("ascii") # Convert into string
            "contentType": str,
            "ratelimitKey": str
                NOTE: Only used by the discord bot Jarvis, the key to use for rate limiting, this could be the user's id, guild's id, etc.
        }

        Returns
        -------
        Inside the "data" key.
        {
            "data": dict,
                The predictions that is returned from nudenet.classify or classify_video. This is not altered in any way so this is the raw prediction.
            "path": str,
                Temporary path it has made, used for keying "data". NOTE: This file is already deleted.
            "contentType": str,
                The content-type. It gets returned back because of the input bytes is a gif, it gets converted onto an mp4 hence why this is returned back to detect the change.
        }
        """

        data = request.json
        data["bytes"] = base64.b64decode(data["bytes"])

        method = "img"
        if data["contentType"].startswith("video/"):
            method = "vid"

        results = {"data": {}, "path": None,
                   "contentType": data["contentType"]}

        suffix = None
        if data["contentType"].lower() == "image/gif":
            suffix = ".gif"
        elif data["contentType"].lower().startswith("video/"):
            mappings = {
                "video/x-msvideo": ".avi",
                "video/mp4": ".mp4",
                "video/mpeg": ".mpeg",
                "video/ogg": ".ogv",
                "video/mp2t": ".ts",
                "video/webm": ".webm",
                "video/x-matroska": ".mkv"
            }
            suffix = mappings.get(data["contentType"].lower(), ".mp4")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            path = tmp.name
            results["path"] = path
            tmp.write(data["bytes"])
            tmp.close()

            oldPath = None
            if suffix == ".gif":
                server.logging.debug("Converting GIF to MP4")
                oldPath = path
                path = f".tmp/{os.path.basename(path)[:-4]}.mp4"

                ff = ffmpy.FFmpeg(
                    inputs={oldPath: None},
                    outputs={path: None}
                )
                ff.run()


                # Update method and metadata
                method = "vid"
                data["contentType"] = "video/mp4"

            results["contentType"] = data["contentType"]
            
            # Get hash and attempt to get its results from the database if it exists
            fromHash = False
            if method == "img":
                contentHash = str(imagehash.average_hash(Image.open(path)))
            elif method == "vid":
                contentHash = VideoHash(path).hash_hex
            
            results["hash"] = contentHash

            stored = server.db.classified_nsfw.find_one({"hash": contentHash})
            if stored:
                server.logging.debug(f"Using hash: {contentHash}")

                fromHash = True
                stored.pop("_id", None)
                
                response = makeResponse(data=stored)

            if not fromHash:
                # Perform classification
                try:
                    nudenet = NudeClassifier()

                    if method == "img":
                        method = nudenet.classify
                    elif method == "vid":
                        method = nudenet.classify_video

                    res = method(path, batch_size=6)
                    del nudenet
                    gc.collect()

                    if data["contentType"].startswith("video/"):
                        newPreds = {}
                        for k, v in res["preds"].items():
                            newPreds[str(k)] = {
                                "safe": float(v["safe"]),
                                "unsafe": float(v["unsafe"])
                            }
                        res["preds"] = newPreds
                    results["data"] = res

                    server.db.classified_nsfw.insert_one(results)
                    results.pop("_id", None)

                    response = makeResponse(data=results)
                except Exception as e:
                    response = makeResponse(status=500, msg=str(e))

            # Delete
            if oldPath:
                os.unlink(oldPath)
            os.unlink(path)
        return response

    return app
