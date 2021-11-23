"""This NSFW detection uses the NudeNet library."""

import base64
import gc
import os
import tempfile
from typing import TYPE_CHECKING

import moviepy.editor as mp
from flask import Blueprint, request
from fluxhelper.flask import makeResponse
from library.schemas import *
from nudenet import NudeClassifier

if TYPE_CHECKING:
    from ..app import Server


def constructNsfw(server: "Server") -> Blueprint:
    app = Blueprint("nsfw_detection", __name__, url_prefix="/nsfw_detection")

    @app.route("/classify", methods=["GET"])
    @server.limiter.limit(2, key="ratelimitKey")
    @server.validator.validate(NSFW_DETECTION_CLASSIFY)
    async def classify():

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

        # nudenet = NudeClassifier()

        # method = nudenet.classify
        # if data["contentType"].startswith("video/"):
        #     method = nudenet.classify_video

        results = {"data": {}, "path": None,
                   "contentType": data["contentType"]}

        suffix = None
        if data["contentType"].lower() == "image/gif":
            suffix = ".gif"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            path = tmp.name
            results["path"] = path
            tmp.write(data["bytes"])
            tmp.close()

            oldPath = None
            if suffix:
                server.logging.debug("Converting GIF to MP4")
                oldPath = path

                clip = mp.VideoFileClip(path)
                path = f".tmp/{os.path.basename(path)[:-4]}.mp4"

                clip.write_videofile(path)
                clip.close()

                # Update method and metadata
                # method = nudenet.classify_video
                data["contentType"] = "video/mp4"

            results["contentType"] = data["contentType"]
        
            # Delete
            if oldPath:
                os.unlink(oldPath)
            os.unlink(path)
            return makeResponse()

            # Perform classification
            try:
                res = method(path, batch_size=2)
                del nudenet
                gc.collect()

                if data["contentType"].startswith("video/"):
                    newPreds = {}
                    for k, v in res["preds"].items():
                        newPreds[k] = {
                            "safe": float(v["safe"]),
                            "unsafe": float(v["unsafe"])
                        }
                    res["preds"] = newPreds
                results["data"] = res
                response = makeResponse(data=results)
            except Exception as e:
                response = makeResponse(status=500, msg=str(e))

            # Delete
            if oldPath:
                os.unlink(oldPath)
            os.unlink(path)
        return response

    return app
