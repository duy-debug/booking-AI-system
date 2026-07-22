# ${message}
#
# Mã revision: ${up_revision}
# Revision trước: ${down_revision | comma,n}
# Ngày tạo: ${create_date}
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


# Áp dụng các thay đổi schema của revision khi nâng cấp cơ sở dữ liệu.
def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


# Hoàn tác các thay đổi schema của revision khi quay về phiên bản trước.
def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
