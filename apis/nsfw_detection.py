"""This NSFW detection uses the NudeNet library."""


import validators
from fastnsfw.classifier import Classifier
from fastnsfw.exceptions import *
from typing import TYPE_CHECKING
from flask import Blueprint, request
from library.schemas import *
from fluxhelper.flask import makeResponse

if TYPE_CHECKING:
    from ..app import Server


MODEL_PATH = "./apis/models/nsfw.299x299.h5"
IMG_SIZE = 299


def constructNsfw(server: "Server") -> Blueprint:
    app = Blueprint("nsfw_detection", __name__, url_prefix="/nsfw_detection")
    classifier = Classifier(
        model=MODEL_PATH,
        logging=server.logging,
        imgSize=(IMG_SIZE, IMG_SIZE),
        frameUniqueness=25,
        workers=20
    )

    @app.route("/classify", methods=["GET"])
    @server.limiter.limit(4, key="ratelimitKey")
    @server.validator.validate(NSFW_DETECTION_CLASSIFY)
    async def classify():

        """
        Classifies an image or video url whether it is NSFW or not.

        Parameters
        ----------
        {
            "url": str,
            "ratelimitKey": str
                NOTE: Only used by the discord bot Jarvis, the key to use for rate limiting, this could be the user's id, guild's id, etc.
        }
        """
        
        inp = request.json
        url = inp.get("url")
        
        if url:
            if not validators.url(url):
                return makeResponse(status=400, msg="invalid url")
        else:
            return makeResponse(status=400, msg="url is required")
        
        try:
            data = classifier.classify(url)
        except InternalRequestError as e:
            return makeResponse(status=400, msg=f"InternalRequestError: {str(e)}")
        except UnknownContentType as e:
            return makeResponse(status=400, msg=f"UnknownContentType: {str(e)}")
        
        return makeResponse(data)

    return app
