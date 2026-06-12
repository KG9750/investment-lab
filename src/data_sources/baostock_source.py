from __future__ import annotations

import contextlib
import io

import pandas as pd

from src.data_sources.base import (
    PriceRequest,
    ProviderError,
    classify_provider_exception,
    provider_symbol_for,
    resolve_adjust,
    standardize_price_frame,
)


class BaoStockSource:
    name = "baostock"

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        if request.market != "CN":
            raise ProviderError(
                f"BaoStock does not handle market {request.market}",
                self.name,
                retryable=False,
                error_type="unsupported_market",
                symbol=request.symbol,
            )
        try:
            import baostock as bs
        except ImportError as exc:
            raise ProviderError(
                "baostock is not installed",
                self.name,
                retryable=False,
                error_type="missing_dependency",
                symbol=request.symbol,
            ) from exc

        adjust, provider_adjust = resolve_adjust(self.name, request.adjust)
        provider_symbol = provider_symbol_for(request.symbol, request.market, self.name)
        fields = "date,open,high,low,close,volume,amount"
        end = request.end if request.end and request.end != "latest" else ""
        with contextlib.redirect_stdout(io.StringIO()):
            login = bs.login()
        if getattr(login, "error_code", "0") != "0":
            message = str(getattr(login, "error_msg", "baostock login failed"))
            raise ProviderError(
                message,
                self.name,
                error_type="login_failed",
                symbol=request.symbol,
            )
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                raw = bs.query_history_k_data_plus(
                    provider_symbol,
                    fields,
                    start_date=request.start,
                    end_date=end,
                    frequency="d",
                    adjustflag=str(provider_adjust),
                )
            if getattr(raw, "error_code", "0") != "0":
                message = str(getattr(raw, "error_msg", "baostock query failed"))
                raise ProviderError(
                    message,
                    self.name,
                    error_type="query_failed",
                    symbol=request.symbol,
                )
            rows = []
            while raw.next():
                rows.append(raw.get_row_data())
            frame = pd.DataFrame(rows, columns=raw.fields)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                str(exc),
                self.name,
                retryable=True,
                error_type=classify_provider_exception(exc),
                symbol=request.symbol,
            ) from exc
        finally:
            with contextlib.redirect_stdout(io.StringIO()):
                bs.logout()
        return standardize_price_frame(
            frame,
            request=request,
            provider=self.name,
            provider_symbol=provider_symbol,
            adjust=adjust,
        )
