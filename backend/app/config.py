from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    earthdata_username: str | None = None
    earthdata_password: SecretStr | None = None
    # Path to a netrc file; exported as NETRC so requests and harmony-py read it.
    netrc: str | None = None
    data_dir: str = "data"
    cors_origins: str = "http://localhost:5173"
    # NISAR COGs cropped in AWS; exported to os.environ for app.services.nisar_s3 and GDAL /vsis3/.
    nisar_bucket: str | None = None
    aws_region: str | None = None

    @property
    def earthdata_auth(self) -> tuple[str, str] | None:
        """EDL (username, password) when both are set; None lets netrc apply."""
        if self.earthdata_password is None:
            return None
        password = self.earthdata_password.get_secret_value()
        if self.earthdata_username and password:
            return self.earthdata_username, password
        return None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
