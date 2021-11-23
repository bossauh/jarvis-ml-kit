from schema import Schema, And, Use, Optional

NSFW_DETECTION_CLASSIFY = Schema({
    "bytes": And(Use(str)),
    "contentType": And(Use(str)),
    Optional("ratelimitKey"): And(Use(str))
})
