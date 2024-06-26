"""
** Stable Diffusion on Beam ** 

The code below shows how to deploy a serverless inference API for running stable diffusion.
"""

from beam import Image, Volume, endpoint, Output

CACHE_PATH = "./models"
BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
REPO = "ByteDance/SDXL-Lightning"
CKPT = "sdxl_lightning_4step_unet.safetensors"
BEAM_OUTPUT_PATH = "/tmp/image.png"


image = Image(
    python_version="python3.9",
    python_packages=[
        "diffusers[torch]>=0.10",
        "transformers",
        "huggingface_hub",
        "torch",
        "pillow",
        "accelerate",
        "safetensors",
        "xformers",
    ],
)


# This runs once when the container first boots
def load_models():
    import torch
    from diffusers import StableDiffusionXLPipeline, UNet2DConditionModel
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file

    # Load model
    unet = UNet2DConditionModel.from_config(BASE_MODEL, subfolder="unet").to(
        "cuda", torch.float16
    )
    unet.load_state_dict(load_file(hf_hub_download(REPO, CKPT)))
    pipe = StableDiffusionXLPipeline.from_pretrained(
        BASE_MODEL,
        unet=unet,
        torch_dtype=torch.float16,
        variant="fp16",
        safety_checker=None,
    )

    pipe.enable_sequential_cpu_offload()
    pipe.enable_attention_slicing("max")

    return pipe


@endpoint(
    image=image,
    on_start=load_models,
    keep_warm_seconds=60,
    cpu=2,
    memory="32Gi",
    gpu="A10G",
    volumes=[Volume(name="models", mount_path=CACHE_PATH)],
)
def generate(context, prompt):
    from diffusers import EulerDiscreteScheduler

    # Retrieve pre-loaded model from loader
    pipe = context.on_start_value

    # Ensure sampler uses "trailing" timesteps
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )

    # Generate image
    image = pipe(prompt, num_inference_steps=4, guidance_scale=0).images[0]
    print(f"Saved Image: {image}")

    # Save image file
    image.save(BEAM_OUTPUT_PATH)
    output = Output(path=BEAM_OUTPUT_PATH)
    output.save()
    # Retrieve pre-signed URL for output file
    url = output.public_url(expires=400)
    print(url)

    return {"image": url}
