"""Perform a minimal OpenRouter call without ever logging the credential."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from data_assistant.llm import MissingAPIKeyError, OpenRouterLLM

EXIT_CONFIGURATION_ERROR = 2
EXIT_PROVIDER_ERROR = 1


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger("smoke_llm")
    try:
        llm = OpenRouterLLM()
    except MissingAPIKeyError as exc:
        logger.error("%s", exc)
        logger.info("Exit code %d indica configuração ausente.", EXIT_CONFIGURATION_ERROR)
        return EXIT_CONFIGURATION_ERROR

    try:
        response = llm.complete(
            "Você verifica conectividade. Responda de forma curta.",
            "Responda somente com OK.",
        )
    except Exception as exc:  # Provider/network errors vary by the selected backend.
        logger.error("Falha operacional ao consultar o OpenRouter: %s", exc)
        return EXIT_PROVIDER_ERROR

    logger.info("OpenRouter respondeu pelo modelo %s: %s", llm.settings.model, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
