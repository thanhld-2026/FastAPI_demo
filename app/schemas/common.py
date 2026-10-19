from pydantic import BaseModel, ConfigDict


class InputSchema(BaseModel):
    """Base cho dữ liệu client gửi lên (request body).

    - str_strip_whitespace: tự cắt khoảng trắng đầu/cuối chuỗi.
    - extra="forbid": gửi field lạ -> 422. Chặn "mass assignment", ví dụ client
      cố gửi {"role": "admin"} khi đăng ký sẽ bị từ chối thay vì bị bỏ qua âm thầm.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ORMSchema(BaseModel):
    """Base cho dữ liệu trả về: from_attributes=True cho phép đọc thẳng từ SQLAlchemy object."""

    model_config = ConfigDict(from_attributes=True)
