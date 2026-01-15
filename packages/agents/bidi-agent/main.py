import asyncio
from strands.experimental.bidi.models import BidiNovaSonicModel


async def main() -> None:
  model = BidiNovaSonicModel(
      model_id="amazon.nova-sonic-v1:0",
      provider_config={
          "audio": {
              "voice": "tiffany",
          },
      },
      client_config={"region": "us-east-1"},  # only available in us-east-1, eu-north-1, and ap-northeast-1
  )
  # stop_conversation tool allows user to verbally stop agent execution.
  agent = BidiAgent(model=model, tools=[calculator, stop_conversation])

  audio_io = BidiAudioIO()
  text_io = BidiTextIO()
  await agent.run(inputs=[audio_io.input()], outputs=[audio_io.output(), text_io.output()])


if __name__ == "__main__":
  asyncio.run(main())
