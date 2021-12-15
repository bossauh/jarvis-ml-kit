from schema import Schema, And, Use, Optional

NSFW_DETECTION_CLASSIFY = Schema({
    "url": And(Use(str)),
    Optional("ratelimitKey"): And(Use(str))
})
